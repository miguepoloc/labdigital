"""Vocabulario compartido por los subcontextos de `teaching` (ARCHITECTURE.md §3.2):
`courses`, `labs` y `submissions` necesitan los mismos ids, quién mira (`Viewer`) y la
escala de notas (la define el lab, la aplica la revisión de la entrega).

`teaching` no importa `identity` ni `projects` (contrato import-linter de independencia):
el usuario llega como el `sub` del access (`UserRef`), igual que `projects.OwnerId`."""

import decimal
import enum
import secrets
from typing import Any, Self
import uuid

from backend.commons.domain import exceptions, value_objects

# Sin caracteres ambiguos al dictarlos o copiarlos a mano: sin 0/O, 1/I/L.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_code(length: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def normalize_code(raw: str, *, length: int) -> str | None:
    """Mayúsculas, sin espacios ni guiones; `None` si no puede ser un código válido."""
    cleaned = "".join(raw.split()).replace("-", "").upper()
    if len(cleaned) != length or any(c not in CODE_ALPHABET for c in cleaned):
        return None
    return cleaned


class CourseId(value_objects.UuidV7Id):
    pass


class LabId(value_objects.UuidV7Id):
    pass


class TeamId(value_objects.UuidV7Id):
    pass


class UserRef(value_objects.ValueObject):
    """Id de un usuario de `identity` (el `sub` del access), sin importar `identity`."""

    value: uuid.UUID

    @classmethod
    def parse(cls, raw: str) -> Self | None:
        try:
            return cls(value=uuid.UUID(raw))
        except ValueError:
            return None

    def __str__(self) -> str:
        return str(self.value)


class Viewer(value_objects.ValueObject):
    """Quién hace la petición: sale SIEMPRE del access verificado, nunca del cuerpo."""

    user_id: UserRef
    is_admin: bool = False


class GradeScaleType(enum.StrEnum):
    NUMERIC = enum.auto()
    PASS_FAIL = enum.auto()


class Grade(value_objects.ValueObject):
    """Una nota ya validada contra su escala: `numeric` (escala numérica) o `passed`
    (aprobado/no aprobado)."""

    numeric: decimal.Decimal | None = None
    passed: bool | None = None

    def as_json(self) -> float | None:
        """Contrato §6.1: numérica tal cual; `pass_fail` ⇒ 1 (aprobado) o 0 (no aprobado)."""
        if self.numeric is not None:
            return float(self.numeric)
        if self.passed is not None:
            return 1 if self.passed else 0
        return None


_MAX_ABS = decimal.Decimal("100000")


def _field_error(fields: dict[str, str]) -> exceptions.ValidationError:
    first = next(iter(fields.values()))
    return exceptions.ValidationError(first, code="validation_error", details={"fields": fields})


def _to_decimal(raw: Any) -> decimal.Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = decimal.Decimal(str(raw))
    except (decimal.InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


class GradeScale(value_objects.ValueObject):
    """Escala de notas definida por el docente para un lab (contrato §4 `grade_scale`).

    - `numeric`: `min < max`, `decimals` 0–2 (por defecto 1), `pass_mark` opcional dentro de
      `[min, max]` y con no más decimales que `decimals`.
    - `pass_fail`: sin `min`/`max`/`decimals`/`pass_mark`.
    Los errores son 422 `validation_error` con `details.fields` (`grade_scale.<campo>`)."""

    type: GradeScaleType
    min: decimal.Decimal | None = None
    max: decimal.Decimal | None = None
    decimals: int | None = None
    pass_mark: decimal.Decimal | None = None

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Self:
        prefix = "grade_scale"
        raw_type = raw.get("type")
        try:
            scale_type = GradeScaleType(str(raw_type))
        except ValueError:
            raise _field_error(
                {f"{prefix}.type": "El tipo de escala debe ser numeric o pass_fail."}
            ) from None
        if scale_type is GradeScaleType.PASS_FAIL:
            extra = [k for k in ("min", "max", "decimals", "pass_mark") if raw.get(k) is not None]
            if extra:
                raise _field_error(
                    {f"{prefix}.{k}": "No aplica a la escala aprobado/no aprobado." for k in extra}
                )
            return cls(type=scale_type)

        fields: dict[str, str] = {}
        low, high = _to_decimal(raw.get("min")), _to_decimal(raw.get("max"))
        if low is None:
            fields[f"{prefix}.min"] = "Indica la nota mínima."
        if high is None:
            fields[f"{prefix}.max"] = "Indica la nota máxima."
        raw_decimals = raw.get("decimals", 1)
        decimals = (
            raw_decimals
            if isinstance(raw_decimals, int) and not isinstance(raw_decimals, bool)
            else None
        )
        if decimals is None or not 0 <= decimals <= 2:
            fields[f"{prefix}.decimals"] = "Los decimales deben ser 0, 1 o 2."
        if low is not None and high is not None:
            if not low < high:
                fields[f"{prefix}.max"] = "La nota máxima debe ser mayor que la mínima."
            if abs(low) > _MAX_ABS or abs(high) > _MAX_ABS:
                fields[f"{prefix}.max"] = "La escala es demasiado grande."
        pass_mark = None
        if raw.get("pass_mark") is not None:
            pass_mark = _to_decimal(raw.get("pass_mark"))
            if pass_mark is None:
                fields[f"{prefix}.pass_mark"] = "La nota de aprobación debe ser un número."
            elif low is not None and high is not None and not low <= pass_mark <= high:
                fields[f"{prefix}.pass_mark"] = (
                    "La nota de aprobación debe estar dentro de la escala."
                )
        if fields:
            raise _field_error(fields)
        assert low is not None and high is not None and decimals is not None
        for name, value in (("min", low), ("max", high), ("pass_mark", pass_mark)):
            if value is not None and _places(value) > decimals:
                fields[f"{prefix}.{name}"] = f"Usa como máximo {decimals} decimal(es)."
        if fields:
            raise _field_error(fields)
        return cls(type=scale_type, min=low, max=high, decimals=decimals, pass_mark=pass_mark)

    def validate_grade(self, raw: Any) -> Grade:
        """Valida una nota contra la escala. 422 con `details.fields.grade`."""
        if self.type is GradeScaleType.PASS_FAIL:
            if isinstance(raw, bool):
                return Grade(passed=raw)
            if isinstance(raw, int | float | decimal.Decimal) and raw in (0, 1):
                return Grade(passed=raw == 1)
            if isinstance(raw, str) and raw.lower() in ("pass", "fail"):
                return Grade(passed=raw.lower() == "pass")
            raise _field_error({"grade": "La nota debe ser 1 (aprobado) o 0 (no aprobado)."})
        assert self.min is not None and self.max is not None and self.decimals is not None
        value = _to_decimal(raw)
        message = (
            f"La nota debe ser un número entre {_fmt(self.min)} y {_fmt(self.max)} "
            f"con máximo {self.decimals} decimal(es)."
        )
        if value is None or not self.min <= value <= self.max or _places(value) > self.decimals:
            error = _field_error({"grade": message})
            error.details.update(
                {"min": float(self.min), "max": float(self.max), "decimals": self.decimals}
            )
            raise error
        return Grade(numeric=value.quantize(decimal.Decimal(1).scaleb(-self.decimals)))

    def to_storage(self) -> dict[str, Any]:
        if self.type is GradeScaleType.PASS_FAIL:
            return {"type": self.type.value}
        return {
            "type": self.type.value,
            "min": float(self.min) if self.min is not None else None,
            "max": float(self.max) if self.max is not None else None,
            "decimals": self.decimals,
            "pass_mark": float(self.pass_mark) if self.pass_mark is not None else None,
        }

    @classmethod
    def from_storage(cls, data: dict[str, Any]) -> Self:
        def dec(key: str) -> decimal.Decimal | None:
            value = data.get(key)
            return None if value is None else decimal.Decimal(str(value))

        return cls(
            type=GradeScaleType(data["type"]),
            min=dec("min"),
            max=dec("max"),
            decimals=data.get("decimals"),
            pass_mark=dec("pass_mark"),
        )


def _places(value: decimal.Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _fmt(value: decimal.Decimal) -> str:
    return format(value.normalize(), "f")
