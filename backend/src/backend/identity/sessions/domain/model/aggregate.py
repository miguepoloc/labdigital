"""`Session` = familia de refresh tokens (plan §Autenticación).

Rotación obligatoria: cada canje válido sustituye `current_token` por uno nuevo. Si llega un
token de la familia que ya fue rotado (reuso), se revoca la sesión entera — quien lo
presenta, o quien lo presentó antes, tiene una copia robada (contrato §2).
"""

import hmac
from typing import Self

from backend.commons.domain import aggregates
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.sessions.domain.model import events, value_objects

_USER_AGENT_MAX = 300


class Redemption(base_value_objects.ValueObject):
    outcome: value_objects.RedeemOutcome
    new_token: value_objects.OpaqueRefreshToken | None = None


class Session(aggregates.AggregateRoot[value_objects.SessionId]):
    user_id: identity_value_objects.UserId
    persistent: bool
    user_agent: str
    ip: str
    credentials_version: int
    last_used_at: base_value_objects.PosixTime
    revoked_at: base_value_objects.PosixTime | None = None
    revoke_reason: value_objects.RevokeReason | None = None
    current_token: value_objects.RefreshTokenRecord

    @classmethod
    def start(
        cls,
        *,
        user_id: identity_value_objects.UserId,
        credentials_version: int,
        persistent: bool,
        user_agent: str,
        ip: str,
    ) -> tuple[Self, value_objects.OpaqueRefreshToken]:
        now = base_value_objects.PosixTime.now()
        record, opaque = _new_token(now, persistent=persistent)
        session = cls(
            id=value_objects.SessionId.new(),
            user_id=user_id,
            persistent=persistent,
            user_agent=user_agent[:_USER_AGENT_MAX],
            ip=ip,
            credentials_version=credentials_version,
            last_used_at=now,
            current_token=record,
            created_at=now,
            updated_at=now,
        )
        session.record_event(events.SessionStarted(session_id=session.id, user_id=user_id))
        return session, opaque

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_active(self) -> bool:
        return (
            not self.is_revoked
            and self.current_token.expires_at > base_value_objects.PosixTime.now()
        )

    def redeem(
        self,
        *,
        presented: value_objects.RefreshTokenRecord,
        secret: str,
        ip: str,
        user_agent: str,
    ) -> Redemption:
        """Decide qué hacer con un refresh presentado de esta familia.

        - secreto incorrecto ⇒ INVALID sin tocar nada (quien sólo conoce el id no puede
          cerrar sesiones ajenas);
        - sesión revocada o token caducado ⇒ INVALID;
        - token ya rotado ⇒ REUSED y la sesión queda revocada;
        - token vigente ⇒ ROTATED con un nuevo token.
        """
        if not hmac.compare_digest(value_objects.hash_secret(secret), presented.token_hash):
            return Redemption(outcome=value_objects.RedeemOutcome.INVALID)
        if self.is_revoked:
            return Redemption(outcome=value_objects.RedeemOutcome.INVALID)
        if presented.id != self.current_token.id or presented.rotated_at is not None:
            self.revoke(value_objects.RevokeReason.REFRESH_REUSE)
            self.record_event(
                events.RefreshTokenReuseDetected(
                    session_id=self.id, user_id=self.user_id, token_id=presented.id
                )
            )
            return Redemption(outcome=value_objects.RedeemOutcome.REUSED)
        now = base_value_objects.PosixTime.now()
        if self.current_token.expires_at <= now:
            return Redemption(outcome=value_objects.RedeemOutcome.INVALID)
        record, opaque = _new_token(now, persistent=self.persistent)
        self.current_token = record
        self.last_used_at = now
        self.ip = ip
        self.user_agent = user_agent[:_USER_AGENT_MAX]
        self.touch()
        return Redemption(outcome=value_objects.RedeemOutcome.ROTATED, new_token=opaque)

    def revoke(self, reason: value_objects.RevokeReason) -> bool:
        """Idempotente; devuelve si cambió algo."""
        if self.is_revoked:
            return False
        self.revoked_at = base_value_objects.PosixTime.now()
        self.revoke_reason = reason
        self.touch()
        self.record_event(
            events.SessionRevoked(session_id=self.id, user_id=self.user_id, reason=reason)
        )
        return True

    def sync_credentials_version(self, credentials_version: int) -> None:
        if credentials_version != self.credentials_version:
            self.credentials_version = credentials_version
            self.touch()

    def refresh_expires_at(self) -> base_value_objects.PosixTime:
        return self.current_token.expires_at


def _new_token(
    now: base_value_objects.PosixTime, *, persistent: bool
) -> tuple[value_objects.RefreshTokenRecord, value_objects.OpaqueRefreshToken]:
    ttl = value_objects.PERSISTENT_TTL if persistent else value_objects.EPHEMERAL_TTL
    secret = value_objects.new_secret()
    token_id = value_objects.RefreshTokenId.new()
    record = value_objects.RefreshTokenRecord(
        id=token_id,
        token_hash=value_objects.hash_secret(secret),
        created_at=now,
        expires_at=base_value_objects.PosixTime.from_datetime(now.to_datetime() + ttl),
    )
    return record, value_objects.OpaqueRefreshToken(token_id=token_id, secret=secret)
