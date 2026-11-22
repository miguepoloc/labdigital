"""`Blob`: un archivo subido por un usuario (informe, bitstream, adjunto). El contenido vive
en el almacenamiento direccionado por SHA-256; esta fila es la "copia" del usuario (dueño,
nombre, tipo). Inmutable tras crearse."""

from typing import Self

from backend.commons.domain import aggregates
from backend.commons.domain import value_objects as base_value_objects
from backend.files.blobs.domain.model import events, exceptions, value_objects


class Blob(aggregates.AggregateRoot[value_objects.BlobId]):
    owner_id: value_objects.OwnerId
    sha256: str
    size: int
    mime: str
    kind: value_objects.FileKind
    name: value_objects.FileName

    @classmethod
    def accept(
        cls,
        *,
        owner_id: value_objects.OwnerId,
        name: value_objects.FileName,
        kind: value_objects.FileKind,
        file_type: value_objects.FileType,
        sha256: str,
        size: int,
        head: bytes,
    ) -> Self:
        if size <= 0:
            raise exceptions.EmptyFileError()
        if size > value_objects.MAX_FILE_BYTES:
            raise exceptions.FileTooLargeError()
        if not value_objects.matches_signature(file_type, head):
            raise exceptions.SignatureMismatchError()
        now = base_value_objects.PosixTime.now()
        blob = cls(
            id=value_objects.BlobId.new(),
            owner_id=owner_id,
            sha256=sha256,
            size=size,
            mime=file_type.mime,
            kind=kind,
            name=name,
            created_at=now,
            updated_at=now,
        )
        blob.record_event(events.BlobUploaded(blob_id=blob.id, owner_id=owner_id, size=size))
        return blob
