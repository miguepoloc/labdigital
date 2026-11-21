import enum
import hashlib
import hmac
import secrets

import pydantic

from backend.commons.domain import exceptions, value_objects

_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16
_EMAIL_ADAPTER = pydantic.TypeAdapter(pydantic.EmailStr)


class UserId(value_objects.HumanFriendlyId):
    """Deliberately `HumanFriendlyId`, not `UuidV7Id` (ARCHITECTURE.md §5.2) — verified
    against `sona-sso-backend`'s real identity aggregates: `ConsoleUserId`, `OrganizationId`,
    `SsoConnectionId` are all `HumanFriendlyId` in the one reference codebase that's actually
    an identity backend, not a fintech-transactions one. A user's ID appears in admin/support
    tooling URLs and audit logs a human reads, the same "genuinely user-facing" case as
    `Order` — a login flow being email-first doesn't change that."""


class Email(value_objects.ValueObject):
    value: str

    @pydantic.field_validator("value")
    @classmethod
    def _validate_format(cls, value: str) -> str:
        """Delegates to `pydantic.EmailStr` (the `email-validator` package, RFC-compliant —
        verified as real, widespread bold precedent: `pydantic.EmailStr` is used directly on
        over a dozen of bold's real DTOs/models) rather than a hand-rolled regex, but still
        raises this codebase's own `exceptions.ValidationError` — the one exception
        vocabulary `commons.adapters.api.exception_handler` maps to HTTP statuses (§13). A
        bare `pydantic.EmailStr` field would raise `pydantic.ValidationError` instead, which
        that handler doesn't know how to map — it would surface as an unhandled 500, not a
        clean 422."""
        try:
            return _EMAIL_ADAPTER.validate_python(value)
        except pydantic.ValidationError as exc:
            raise exceptions.ValidationError(
                f"[{value}] is not a valid email address.", code="INVALID_EMAIL"
            ) from exc

    def __str__(self) -> str:
        return self.value


class HashedPassword(value_objects.ValueObject):
    """Never store or compare a plaintext password — this VO is the only place a password
    is hashed or verified (ARCHITECTURE.md §1.11's rule applied to auth specifically)."""

    salt_hex: str
    hash_hex: str

    @classmethod
    def hash_plaintext(cls, plaintext: str) -> "HashedPassword":
        salt = secrets.token_bytes(_SALT_BYTES)
        digest = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, _PBKDF2_ITERATIONS)
        return cls(salt_hex=salt.hex(), hash_hex=digest.hex())

    def matches(self, plaintext: str) -> bool:
        salt = bytes.fromhex(self.salt_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, _PBKDF2_ITERATIONS)
        return hmac.compare_digest(candidate.hex(), self.hash_hex)


class RefreshTokenId(value_objects.UuidV7Id):
    pass


class AuditAggregateType(enum.StrEnum):
    """Local to `identity.users` — `commons.domain.audit.AuditEntry.aggregate_type` stores
    whatever `.value` this produces, but `commons/` never imports this enum (contract 4):
    growth of what `identity.users` can audit stays in this file, never `commons/`."""

    USER = enum.auto()


class AuditAction(enum.StrEnum):
    """Same rule as `AuditAggregateType` — grows here, not in `commons/`."""

    REGISTERED = enum.auto()
    DEACTIVATED = enum.auto()
