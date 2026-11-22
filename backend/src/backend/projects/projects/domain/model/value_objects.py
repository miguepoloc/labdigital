import datetime
import enum
import json
from typing import Any
import uuid

import pydantic

from backend.commons.domain import exceptions, value_objects

MAX_CONTENT_BYTES = 2 * 1024 * 1024  # contrato §5 (= MAX_PROJECT_BYTES de JG FPGA)
AUTOSAVE_WINDOW = datetime.timedelta(minutes=10)
_NAME_MAX = 120
_LABEL_MAX = 120


class ProjectId(value_objects.UuidV7Id):
    pass


class ProjectVersionId(value_objects.UuidV7Id):
    pass


class OwnerId(value_objects.ValueObject):
    """Id del usuario dueño (el `sub` del access). Propio de `projects`: este contexto no
    importa `identity` (contrato import-linter de independencia)."""

    value: uuid.UUID

    def __str__(self) -> str:
        return str(self.value)


class Module(enum.StrEnum):
    FPGA = enum.auto()


# Formato de `content` aceptado por módulo (contrato §5).
_FORMAT_FOR_MODULE = {Module.FPGA: "basys3-sim-project"}


class VersionKind(enum.StrEnum):
    AUTOSAVE = enum.auto()
    MANUAL = enum.auto()
    # Congelada por una entrega (contrato §6.1): inmutable (`locked`).
    SUBMITTED = enum.auto()


class ProjectName(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not 1 <= len(cleaned) <= _NAME_MAX:
            raise exceptions.ValidationError(
                f"El nombre del proyecto debe tener entre 1 y {_NAME_MAX} caracteres.",
                code="validation_error",
                details={"field": "name"},
            )
        return cleaned


class VersionLabel(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) > _LABEL_MAX:
            raise exceptions.ValidationError(
                f"La etiqueta no puede superar {_LABEL_MAX} caracteres.",
                code="validation_error",
                details={"field": "label"},
            )
        return cleaned


class ProjectContent(value_objects.ValueObject):
    """JSON opaco del módulo (contrato §5), validado sólo por tamaño y `format`."""

    data: dict[str, Any]
    size: int

    @classmethod
    def for_module(cls, module: Module, data: Any) -> "ProjectContent":
        if not isinstance(data, dict):
            raise exceptions.ValidationError(
                "El contenido del proyecto debe ser un objeto JSON.",
                code="validation_error",
                details={"field": "content"},
            )
        size = len(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode())
        if size > MAX_CONTENT_BYTES:
            raise exceptions.PayloadTooLargeError("El proyecto supera el tamaño máximo de 2 MB.")
        expected = _FORMAT_FOR_MODULE[module]
        if data.get("format") != expected:
            raise exceptions.ValidationError(
                f'El contenido debe tener "format": "{expected}".',
                code="validation_error",
                details={"field": "content.format", "expected": expected},
            )
        return cls(data=data, size=size)
