"""Refresh-token storage — ARCHITECTURE.md §9.3. Persistence-only, not a domain aggregate
(see the docstring on RefreshTokenOrm for why); services/auth.py is the only caller."""

import datetime
import hashlib
import secrets
import typing
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.commons.domain import value_objects as base_value_objects
from backend.identity.users.adapters import orm
from backend.identity.users.domain.model import exceptions, value_objects

REFRESH_TOKEN_TTL = datetime.timedelta(days=30)
_TOKEN_SECRET_BYTES = 32


def issue(session: Session, *, user_id: value_objects.UserId) -> str:
    """Returns the opaque token to hand to the client — `"<token_id>.<secret>"`. Only the
    SHA-256 hash of the secret is stored; a stolen DB backup can't be replayed as a token."""
    token_id = uuid.uuid4()
    secret = secrets.token_urlsafe(_TOKEN_SECRET_BYTES)
    now = base_value_objects.PosixTime.now()
    expires_at = base_value_objects.PosixTime.from_datetime(now.to_datetime() + REFRESH_TOKEN_TTL)
    session.add(
        orm.RefreshTokenOrm(
            id=token_id,
            user_id=user_id.value,
            token_hash=_hash(secret),
            expires_at=expires_at.microseconds,
            revoked_at=None,
            created_at=now.microseconds,
            updated_at=now.microseconds,
        )
    )
    return f"{token_id}.{secret}"


def redeem(session: Session, *, opaque_token: str) -> value_objects.UserId:
    """Validates a refresh token and returns the user it belongs to. Raises
    RefreshTokenNotFoundError for any invalid/expired/revoked/malformed token — deliberately
    one error for all of these, so a client can't distinguish "wrong secret" from "expired"
    from "doesn't exist" (that distinction is exactly what an attacker would want)."""
    try:
        token_id_str, secret = opaque_token.split(".", 1)
        token_id = uuid.UUID(token_id_str)
    except ValueError as exc:
        raise exceptions.RefreshTokenNotFoundError() from exc

    row = session.get(orm.RefreshTokenOrm, token_id)
    now = base_value_objects.PosixTime.now()
    if (
        row is None
        or row.revoked_at is not None
        or row.expires_at < now.microseconds
        or row.token_hash != _hash(secret)
    ):
        raise exceptions.RefreshTokenNotFoundError()
    return value_objects.UserId(value=row.user_id)


def revoke_all_for_user(session: Session, *, user_id: value_objects.UserId) -> None:
    """Called from deactivate_user (ARCHITECTURE.md §9.3) so a deactivated user's existing
    sessions die immediately, without commerce or any other product ever calling back
    identity."""
    now = base_value_objects.PosixTime.now().microseconds
    session.execute(
        sa.update(orm.RefreshTokenOrm)
        .where(
            orm.RefreshTokenOrm.user_id == user_id.value, orm.RefreshTokenOrm.revoked_at.is_(None)
        )
        .values(revoked_at=now, updated_at=now)
    )


def expire_stale(session: Session) -> int:
    """Called from the cron entrypoint (ARCHITECTURE.md §9.5/§18) — housekeeping, deletes
    rows that expired more than a day ago so the table doesn't grow forever."""
    now = base_value_objects.PosixTime.now()
    cutoff = now.microseconds - int(datetime.timedelta(days=1).total_seconds() * 1_000_000)
    result = session.execute(
        sa.delete(orm.RefreshTokenOrm).where(orm.RefreshTokenOrm.expires_at < cutoff)
    )
    # DELETE always returns a CursorResult at runtime; the stub types session.execute()
    # more broadly as Result[Any], which doesn't declare .rowcount.
    return typing.cast(sa.CursorResult, result).rowcount


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
