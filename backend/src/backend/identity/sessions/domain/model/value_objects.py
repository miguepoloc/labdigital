import datetime
import enum
import hashlib
import secrets
import uuid

from backend.commons.domain import value_objects

PERSISTENT_TTL = datetime.timedelta(days=30)
# `remember=false`: la cookie es de sesión del navegador y, en el servidor, el refresh caduca
# tras 24 h sin uso (cada rotación lo renueva).
EPHEMERAL_TTL = datetime.timedelta(hours=24)
_SECRET_BYTES = 32
# Contrato §6.1 "Refresh concurrente": reusar el refresh recién rotado dentro de esta ventana
# (dos pestañas renovando a la vez) no es robo; fuera de ella sí.
REUSE_GRACE = datetime.timedelta(seconds=10)


class SessionId(value_objects.UuidV7Id):
    pass


class RefreshTokenId(value_objects.UuidV7Id):
    pass


class RevokeReason(enum.StrEnum):
    LOGOUT = enum.auto()
    REVOKED_BY_USER = enum.auto()
    REVOKED_OTHERS = enum.auto()
    PASSWORD_RESET = enum.auto()
    PASSWORD_CHANGED = enum.auto()
    REFRESH_REUSE = enum.auto()
    USER_INACTIVE = enum.auto()
    CREDENTIALS_CHANGED = enum.auto()


class RefreshTokenRecord(value_objects.ValueObject):
    """Un eslabón de la familia de refresh de una sesión. Sólo se guarda el hash."""

    id: RefreshTokenId
    token_hash: str
    created_at: value_objects.PosixTime
    expires_at: value_objects.PosixTime
    rotated_at: value_objects.PosixTime | None = None


class OpaqueRefreshToken(value_objects.ValueObject):
    """`<uuid>.<secreto>` (contrato §2)."""

    token_id: RefreshTokenId
    secret: str

    @classmethod
    def parse(cls, raw: str) -> "OpaqueRefreshToken | None":
        try:
            token_id_str, secret = raw.split(".", 1)
            return cls(token_id=RefreshTokenId(value=uuid.UUID(token_id_str)), secret=secret)
        except ValueError:
            return None

    def __str__(self) -> str:
        return f"{self.token_id}.{self.secret}"


class RedeemOutcome(enum.StrEnum):
    ROTATED = enum.auto()
    # Refresh ya rotado presentado dentro de `REUSE_GRACE`: se emite otro de la misma familia.
    ROTATED_IN_GRACE = enum.auto()
    REUSED = enum.auto()
    INVALID = enum.auto()


def new_secret() -> str:
    return secrets.token_urlsafe(_SECRET_BYTES)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class AuditAggregateType(enum.StrEnum):
    SESSION = enum.auto()


class AuditAction(enum.StrEnum):
    REFRESH_REUSE_DETECTED = enum.auto()
    SESSION_REVOKED = enum.auto()
