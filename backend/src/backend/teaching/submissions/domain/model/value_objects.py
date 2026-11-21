import enum
import uuid

import pydantic

from backend.commons.domain import exceptions, value_objects

MAX_SUBMISSION_BYTES = 100 * 1024 * 1024  # contrato §4: 100 MB por entrega
MAX_FILES = 20
_COMMENT_MAX = 10_000


class SubmissionId(value_objects.UuidV7Id):
    pass


class ReviewId(value_objects.UuidV7Id):
    pass


class SubmissionStatus(enum.StrEnum):
    SUBMITTED = enum.auto()
    RETURNED = enum.auto()  # devuelta para corregir: admite re-entrega
    GRADED = enum.auto()


class FileKind(enum.StrEnum):
    REPORT = enum.auto()
    BITSTREAM = enum.auto()
    ATTACHMENT = enum.auto()


class SubmissionFile(value_objects.ValueObject):
    """Referencia a un blob de `files` (el contenido nunca pasa por aquí)."""

    blob_id: uuid.UUID
    kind: FileKind
    size: int
    name: str


class FrozenProject(value_objects.ValueObject):
    """La versión del proyecto congelada (bloqueada en `projects`) que se entregó."""

    project_id: uuid.UUID
    project_name: str
    version_id: uuid.UUID
    version_n: int


class Comment(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) > _COMMENT_MAX:
            raise exceptions.ValidationError(
                f"El comentario no puede superar {_COMMENT_MAX} caracteres.",
                code="validation_error",
                details={"field": "comment"},
            )
        return cleaned


class AuditAggregateType(enum.StrEnum):
    SUBMISSION = enum.auto()


class AuditAction(enum.StrEnum):
    SUBMITTED = enum.auto()
    REVIEWED = enum.auto()
