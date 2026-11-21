import enum

import pydantic

from backend.commons.domain import exceptions, value_objects
from backend.teaching.commons import value_objects as teaching_value_objects

JOIN_CODE_LENGTH = 8
_NAME_MAX = 120
_PERIOD_MAX = 40
_DESCRIPTION_MAX = 4000


class MembershipId(value_objects.UuidV7Id):
    pass


class MembershipRole(enum.StrEnum):
    """Rol dentro de un curso (plan §Decisiones): quien lo crea es `docente`."""

    DOCENTE = enum.auto()
    ESTUDIANTE = enum.auto()


class MembershipStatus(enum.StrEnum):
    PENDING = enum.auto()
    ACTIVE = enum.auto()
    REJECTED = enum.auto()
    REMOVED = enum.auto()


class JoinCode(value_objects.ValueObject):
    """Código corto del curso: 8 caracteres de `CODE_ALPHABET` (sin 0/O/1/I/L). Se muestra
    como `ABCD-EFGH`; al unirse se acepta con o sin guion, en minúsculas o con espacios."""

    value: str

    @classmethod
    def new(cls) -> "JoinCode":
        return cls(value=teaching_value_objects.new_code(JOIN_CODE_LENGTH))

    @classmethod
    def parse(cls, raw: str) -> "JoinCode | None":
        normalized = teaching_value_objects.normalize_code(raw, length=JOIN_CODE_LENGTH)
        return None if normalized is None else cls(value=normalized)

    @property
    def display(self) -> str:
        return f"{self.value[:4]}-{self.value[4:]}"


def _clean(value: str, *, field: str, label: str, low: int, high: int) -> str:
    cleaned = " ".join(value.split())
    if not low <= len(cleaned) <= high:
        raise exceptions.ValidationError(
            f"{label} debe tener entre {low} y {high} caracteres.",
            code="validation_error",
            details={"field": field},
        )
    return cleaned


class CourseName(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        return _clean(value, field="name", label="El nombre", low=1, high=_NAME_MAX)


class Period(value_objects.ValueObject):
    """Periodo académico libre (p. ej. `2027-I`)."""

    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        return _clean(value, field="period", label="El periodo", low=1, high=_PERIOD_MAX)


class Description(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) > _DESCRIPTION_MAX:
            raise exceptions.ValidationError(
                f"La descripción no puede superar {_DESCRIPTION_MAX} caracteres.",
                code="validation_error",
                details={"field": "description"},
            )
        return cleaned


class MembershipDecision(enum.StrEnum):
    APPROVE = enum.auto()
    REJECT = enum.auto()
    REMOVE = enum.auto()


class AuditAggregateType(enum.StrEnum):
    COURSE = enum.auto()
    MEMBERSHIP = enum.auto()


class AuditAction(enum.StrEnum):
    COURSE_CREATED = enum.auto()
    COURSE_UPDATED = enum.auto()
    COURSE_ARCHIVED = enum.auto()
    COURSE_UNARCHIVED = enum.auto()
    JOIN_CODE_ROTATED = enum.auto()
    JOIN_REQUESTED = enum.auto()
    MEMBERSHIP_APPROVED = enum.auto()
    MEMBERSHIP_REJECTED = enum.auto()
    MEMBERSHIP_REMOVED = enum.auto()
