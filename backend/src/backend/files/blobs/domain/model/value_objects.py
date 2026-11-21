"""Tipos de archivo admitidos (contrato §4): `.bit .pdf .docx .png .jpg .jpeg .mp4`, 25 MB.

El tipo lo decide el SERVIDOR: extensión permitida Y firma mágica de los primeros bytes
(un `.pdf` que no empieza por `%PDF-` se rechaza). `.bit` (bitstream de Xilinx) no tiene una
firma fija fiable: sólo se comprueba extensión, tamaño > 0 y ≤ 25 MB. El `mime` que se guarda
y se sirve sale de la extensión, nunca del cliente."""

import enum
import uuid

import pydantic

from backend.commons.domain import exceptions, value_objects

MAX_FILE_BYTES = 25 * 1024 * 1024
SNIFF_BYTES = 16
_NAME_MAX = 200


class BlobId(value_objects.UuidV7Id):
    pass


class OwnerId(value_objects.ValueObject):
    value: uuid.UUID

    def __str__(self) -> str:
        return str(self.value)


class FileKind(enum.StrEnum):
    REPORT = enum.auto()
    BITSTREAM = enum.auto()
    ATTACHMENT = enum.auto()


class FileType(value_objects.ValueObject):
    extension: str
    mime: str


_TYPES = {
    ".bit": "application/octet-stream",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".mp4": "video/mp4",
}
# Qué extensiones admite cada `kind` (un informe es un documento; un bitstream, un `.bit`).
_KIND_EXTENSIONS = {
    FileKind.BITSTREAM: {".bit"},
    FileKind.REPORT: {".pdf", ".docx"},
    FileKind.ATTACHMENT: set(_TYPES),
}


class FileName(value_objects.ValueObject):
    """Nombre original saneado (sin rutas ni caracteres de control); se usa sólo para el
    `Content-Disposition` de la descarga."""

    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        base = value.replace("\\", "/").rsplit("/", 1)[-1]
        cleaned = "".join(c for c in base if c.isprintable() and c not in '"<>|:*?').strip()
        if not cleaned or cleaned.startswith("."):
            raise exceptions.ValidationError(
                "Nombre de archivo no válido.", code="validation_error", details={"field": "file"}
            )
        if len(cleaned) > _NAME_MAX:
            stem, dot, ext = cleaned.rpartition(".")
            cleaned = (stem[: _NAME_MAX - len(ext) - 1] + dot + ext) if dot else cleaned[:_NAME_MAX]
        return cleaned

    @property
    def extension(self) -> str:
        _, dot, ext = self.value.rpartition(".")
        return f".{ext.lower()}" if dot else ""


def resolve_type(name: FileName, kind: FileKind) -> FileType:
    """422 si la extensión no está permitida o no corresponde al `kind`."""
    ext = name.extension
    if ext not in _TYPES:
        raise exceptions.ValidationError(
            "Tipo de archivo no permitido (.bit, .pdf, .docx, .png, .jpg, .jpeg, .mp4).",
            code="validation_error",
            details={"field": "file"},
        )
    if ext not in _KIND_EXTENSIONS[kind]:
        raise exceptions.ValidationError(
            f"Un archivo de tipo {kind.value} no puede ser {ext}.",
            code="validation_error",
            details={"field": "kind"},
        )
    return FileType(extension=ext, mime=_TYPES[ext])


def matches_signature(file_type: FileType, head: bytes) -> bool:
    """Firma mágica básica de los primeros bytes."""
    ext = file_type.extension
    if ext == ".pdf":
        return head.startswith(b"%PDF-")
    if ext == ".docx":
        return head.startswith(b"PK\x03\x04")  # contenedor zip (OOXML)
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".mp4":
        return len(head) >= 8 and head[4:8] == b"ftyp"
    return ext == ".bit"  # sin firma fija


class AuditAggregateType(enum.StrEnum):
    BLOB = enum.auto()


class AuditAction(enum.StrEnum):
    UPLOADED = enum.auto()
