import enum

import pydantic

from backend.commons.domain import exceptions, value_objects
from backend.teaching.commons import value_objects as teaching_value_objects

TEAM_CODE_LENGTH = 6
MAX_TEAM_SIZE = 10
_TITLE_MAX = 200
_STATEMENT_MAX = 200_000
_TEAM_NAME_MAX = 80


class LabModule(enum.StrEnum):
    """Módulo con el que se resuelve el lab (hoy sólo la FPGA). Propio de `teaching`: no
    importa `projects` (contrato import-linter de independencia)."""

    FPGA = enum.auto()


class DeadlinePolicy(enum.StrEnum):
    STRICT = enum.auto()  # tras `due_at` no se admite (409 `deadline_passed`)
    LATE_MARKED = enum.auto()  # se admite y queda `is_late`
    NONE = enum.auto()  # sin fecha límite


class TeamMode(enum.StrEnum):
    INDIVIDUAL = enum.auto()
    TEAM = enum.auto()


class LabTitle(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not 1 <= len(cleaned) <= _TITLE_MAX:
            raise exceptions.ValidationError(
                f"El título debe tener entre 1 y {_TITLE_MAX} caracteres.",
                code="validation_error",
                details={"field": "title"},
            )
        return cleaned


class StatementMd(value_objects.ValueObject):
    """Enunciado en Markdown, guardado TAL CUAL: el render seguro (sanitizado) es del
    frontend; la API nunca lo interpreta ni lo devuelve como HTML."""

    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        if len(value) > _STATEMENT_MAX:
            raise exceptions.ValidationError(
                f"El enunciado no puede superar {_STATEMENT_MAX} caracteres.",
                code="validation_error",
                details={"field": "statement_md"},
            )
        return value


class Schedule(value_objects.ValueObject):
    """Fechas y política. `strict`/`late_marked` exigen `due_at`; `opens_at < due_at`."""

    opens_at: value_objects.PosixTime | None = None
    due_at: value_objects.PosixTime | None = None
    deadline_policy: DeadlinePolicy

    @pydantic.model_validator(mode="after")
    def _validate(self) -> "Schedule":
        if self.deadline_policy is not DeadlinePolicy.NONE and self.due_at is None:
            raise exceptions.ValidationError(
                "Con cierre estricto o tardía marcada hay que indicar la fecha límite.",
                code="validation_error",
                details={"field": "due_at"},
            )
        if self.opens_at and self.due_at and not self.opens_at < self.due_at:
            raise exceptions.ValidationError(
                "La fecha de apertura debe ser anterior a la fecha límite.",
                code="validation_error",
                details={"field": "opens_at"},
            )
        return self


class TeamSetup(value_objects.ValueObject):
    """`team` exige `max_team_size` entre 2 y 10; `individual` no lo admite."""

    team_mode: TeamMode
    max_team_size: int | None = None

    @pydantic.model_validator(mode="after")
    def _validate(self) -> "TeamSetup":
        if self.team_mode is TeamMode.TEAM:
            if self.max_team_size is None or not 2 <= self.max_team_size <= MAX_TEAM_SIZE:
                raise exceptions.ValidationError(
                    f"El tamaño máximo del equipo debe estar entre 2 y {MAX_TEAM_SIZE}.",
                    code="validation_error",
                    details={"field": "max_team_size"},
                )
        elif self.max_team_size is not None:
            raise exceptions.ValidationError(
                "Un laboratorio individual no tiene tamaño de equipo.",
                code="validation_error",
                details={"field": "max_team_size"},
            )
        return self


class TeamName(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not 1 <= len(cleaned) <= _TEAM_NAME_MAX:
            raise exceptions.ValidationError(
                f"El nombre del equipo debe tener entre 1 y {_TEAM_NAME_MAX} caracteres.",
                code="validation_error",
                details={"field": "name"},
            )
        return cleaned


class TeamJoinCode(value_objects.ValueObject):
    """6 caracteres sin ambiguos; único dentro del lab."""

    value: str

    @classmethod
    def new(cls) -> "TeamJoinCode":
        return cls(value=teaching_value_objects.new_code(TEAM_CODE_LENGTH))

    @classmethod
    def parse(cls, raw: str) -> "TeamJoinCode | None":
        normalized = teaching_value_objects.normalize_code(raw, length=TEAM_CODE_LENGTH)
        return None if normalized is None else cls(value=normalized)


class AuditAggregateType(enum.StrEnum):
    LAB = enum.auto()
    TEAM = enum.auto()


class AuditAction(enum.StrEnum):
    LAB_CREATED = enum.auto()
    LAB_UPDATED = enum.auto()
    LAB_PUBLISHED = enum.auto()
    TEAM_MEMBERS_SET = enum.auto()
    TEAM_LOCKED = enum.auto()
    TEAM_UNLOCKED = enum.auto()
