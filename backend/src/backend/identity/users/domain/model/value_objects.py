import enum
import hashlib
import secrets

import argon2
from argon2 import exceptions as argon2_exceptions
import pydantic

from backend.commons.domain import exceptions, value_objects

_EMAIL_ADAPTER = pydantic.TypeAdapter(pydantic.EmailStr)
_TOKEN_SECRET_BYTES = 32
_FULL_NAME_MAX = 120

# Argon2id con los parámetros por defecto de argon2-cffi (RFC 9106, perfil "low memory":
# t=3, m=64 MiB, p=4). `HashedPassword.needs_rehash()` detecta hashes con parámetros
# antiguos y el login los re-hashea de forma transparente.
_HASHER = argon2.PasswordHasher()


class Email(value_objects.ValueObject):
    """Normalizado: sin espacios y en minúsculas (la unicidad en BD es sobre este valor)."""

    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate_format(cls, value: str) -> str:
        candidate = value.strip().lower()
        try:
            return str(_EMAIL_ADAPTER.validate_python(candidate)).lower()
        except pydantic.ValidationError as exc:
            raise exceptions.ValidationError(
                "El correo no es válido.",
                code="validation_error",
                details={"field": "email", "reason": "invalid"},
            ) from exc

    def __str__(self) -> str:
        return self.value


class FullName(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not 2 <= len(cleaned) <= _FULL_NAME_MAX:
            raise exceptions.ValidationError(
                f"El nombre completo debe tener entre 2 y {_FULL_NAME_MAX} caracteres.",
                code="validation_error",
                details={"field": "full_name", "reason": "length"},
            )
        return cleaned

    def __str__(self) -> str:
        return self.value


class HashedPassword(value_objects.ValueObject):
    """Único lugar donde se hashea o compara una contraseña. `encoded` es la cadena PHC de
    Argon2id (`$argon2id$v=19$m=...,t=...,p=...$salt$hash`)."""

    encoded: str

    @classmethod
    def hash_plaintext(cls, plaintext: str) -> "HashedPassword":
        return cls(encoded=_HASHER.hash(plaintext))

    def matches(self, plaintext: str) -> bool:
        try:
            return _HASHER.verify(self.encoded, plaintext)
        except (argon2_exceptions.VerificationError, argon2_exceptions.InvalidHashError):
            return False

    def needs_rehash(self) -> bool:
        return _HASHER.check_needs_rehash(self.encoded)


def burn_password_check(plaintext: str) -> None:
    """Gasta el mismo tiempo que una verificación real cuando el correo no existe, para que
    el tiempo de respuesta no revele si la cuenta existe."""
    _HASHER.hash(plaintext)


class DataPolicyAcceptance(value_objects.ValueObject):
    """Aceptación de la política de tratamiento de datos (Ley 1581/2012)."""

    version: str
    accepted_at: value_objects.PosixTime


class EmailTokenId(value_objects.UuidV7Id):
    pass


class EmailTokenPurpose(enum.StrEnum):
    VERIFY_EMAIL = enum.auto()
    PASSWORD_RESET = enum.auto()


def new_token_secret() -> str:
    return secrets.token_urlsafe(_TOKEN_SECRET_BYTES)


def hash_token_secret(secret: str) -> str:
    """Sólo se guarda el SHA-256: un respaldo robado de la BD no sirve para usar enlaces."""
    return hashlib.sha256(secret.encode()).hexdigest()


class AuditAggregateType(enum.StrEnum):
    USER = enum.auto()


class AuditAction(enum.StrEnum):
    REGISTERED = enum.auto()
    EMAIL_VERIFIED = enum.auto()
    LOGIN_SUCCEEDED = enum.auto()
    LOGIN_FAILED = enum.auto()
    PASSWORD_RESET_REQUESTED = enum.auto()
    PASSWORD_RESET = enum.auto()
    PASSWORD_CHANGED = enum.auto()
    PASSWORD_REHASHED = enum.auto()
    ROLE_CHANGED = enum.auto()
    PROFILE_UPDATED = enum.auto()
    DEACTIVATED = enum.auto()
    ACTIVATED = enum.auto()
