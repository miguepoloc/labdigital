"""Almacenamiento en disco direccionado por contenido (`BLOB_DIR`, volumen
`labdigital-blobs`). Escribe primero en `BLOB_DIR/tmp/` (mismo sistema de ficheros) y
renombra atómicamente a `BLOB_DIR/<sha[0:2]>/<sha[2:4]>/<sha>`."""

import contextlib
import hashlib
import os
import secrets
from typing import BinaryIO

from backend.files.blobs.domain.model import exceptions, ports, value_objects

_CHUNK = 1024 * 1024


class FilesystemBlobStorage(ports.BlobStorage):
    def __init__(self, base_dir: str) -> None:
        self._base = os.path.abspath(base_dir)

    def receive(self, stream: BinaryIO, *, max_bytes: int) -> ports.ReceivedContent:
        tmp_dir = os.path.join(self._base, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        temp_path = os.path.join(tmp_dir, secrets.token_hex(16))
        digest = hashlib.sha256()
        size = 0
        head = b""
        try:
            with open(temp_path, "wb") as out:
                while chunk := stream.read(_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise exceptions.FileTooLargeError()
                    if len(head) < value_objects.SNIFF_BYTES:
                        head += chunk[: value_objects.SNIFF_BYTES - len(head)]
                    digest.update(chunk)
                    out.write(chunk)
        except BaseException:
            _remove(temp_path)
            raise
        return ports.ReceivedContent(
            temp_ref=temp_path, sha256=digest.hexdigest(), size=size, head=head
        )

    def keep(self, received: ports.ReceivedContent) -> None:
        final = self.path_for(received.sha256)
        if os.path.exists(final):
            _remove(received.temp_ref)
            return
        os.makedirs(os.path.dirname(final), exist_ok=True)
        os.replace(received.temp_ref, final)

    def discard(self, received: ports.ReceivedContent) -> None:
        _remove(received.temp_ref)

    def path_for(self, sha256: str) -> str:
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise exceptions.BlobNotFoundError()
        return os.path.join(self._base, sha256[:2], sha256[2:4], sha256)


def _remove(path: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.remove(path)
