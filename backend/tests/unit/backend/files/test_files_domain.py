import io
import os
import tempfile
import uuid

import pytest

from backend.commons.adapters.api import middleware
from backend.commons.domain import exceptions as commons_exceptions
from backend.files.blobs.adapters import storage
from backend.files.blobs.domain.model import aggregate, exceptions, value_objects

pytestmark = pytest.mark.unit

OWNER = value_objects.OwnerId(value=uuid.uuid4())


def _accept(name: str, kind: str, head: bytes, size: int = 100) -> aggregate.Blob:
    file_name = value_objects.FileName(value=name)
    file_kind = value_objects.FileKind(kind)
    return aggregate.Blob.accept(
        owner_id=OWNER,
        name=file_name,
        kind=file_kind,
        file_type=value_objects.resolve_type(file_name, file_kind),
        sha256="a" * 64,
        size=size,
        head=head,
    )


@pytest.mark.parametrize(
    ("name", "head", "mime"),
    [
        ("i.pdf", b"%PDF-1.7", "application/pdf"),
        (
            "i.DOCX",
            b"PK\x03\x04\x14\x00",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("f.png", b"\x89PNG\r\n\x1a\n", "image/png"),
        ("f.jpeg", b"\xff\xd8\xff\xe0", "image/jpeg"),
        ("v.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4"),
        ("t.bit", b"\x00\x09\x0f", "application/octet-stream"),
    ],
)
def test_allowed_types_with_signature(name: str, head: bytes, mime: str) -> None:
    kind = "bitstream" if name.endswith(".bit") else "attachment"
    assert _accept(name, kind, head).mime == mime


def test_fake_signature_wrong_kind_and_limits_are_rejected() -> None:
    with pytest.raises(exceptions.SignatureMismatchError):
        _accept("informe.pdf", "report", b"MZ\x90\x00")
    with pytest.raises(exceptions.SignatureMismatchError):
        _accept("foto.png", "attachment", b"\xff\xd8\xff")  # jpg disfrazado de png
    with pytest.raises(commons_exceptions.ValidationError):
        _accept("informe.png", "report", b"\x89PNG\r\n\x1a\n")  # un informe no es png
    with pytest.raises(commons_exceptions.ValidationError):
        _accept("x.exe", "attachment", b"MZ")
    with pytest.raises(exceptions.EmptyFileError):
        _accept("t.bit", "bitstream", b"", size=0)
    with pytest.raises(exceptions.FileTooLargeError):
        _accept("t.bit", "bitstream", b"\x00", size=value_objects.MAX_FILE_BYTES + 1)
    assert value_objects.FileName(value="../../etc/pass?wd.pdf").value == "passwd.pdf"


def test_filesystem_storage_streams_hashes_dedupes_and_cuts_at_limit() -> None:
    with tempfile.TemporaryDirectory(prefix="ld-test-b2-") as base:
        store = storage.FilesystemBlobStorage(base)
        first = store.receive(io.BytesIO(b"hola"), max_bytes=10)
        assert first.head == b"hola" and first.size == 4
        store.keep(first)
        second = store.receive(io.BytesIO(b"hola"), max_bytes=10)
        store.keep(second)  # mismo contenido: se descarta el temporal
        path = store.path_for(first.sha256)
        with open(path, "rb") as stored:
            assert stored.read() == b"hola"
        assert os.listdir(os.path.join(base, "tmp")) == []
        with pytest.raises(exceptions.FileTooLargeError):
            store.receive(io.BytesIO(b"x" * 11), max_bytes=10)
        assert os.listdir(os.path.join(base, "tmp")) == []
        with pytest.raises(exceptions.BlobNotFoundError):
            store.path_for("../../etc/passwd")


def test_body_limit_override_only_for_file_upload() -> None:
    limiter = middleware.BodySizeLimitMiddleware(
        app=lambda *_: None,  # type: ignore[arg-type]
        max_bytes=3,
        overrides={("POST", "/v1/files"): 25},
    )
    assert limiter._limit_for("POST", "/labdigital/api/v1/files") == 25
    assert limiter._limit_for("POST", "/v1/files/") == 25
    assert limiter._limit_for("GET", "/v1/files") == 3
    assert limiter._limit_for("POST", "/v1/projects") == 3
