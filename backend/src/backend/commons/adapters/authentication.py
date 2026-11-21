"""RS256 JWT issuance + validation — ARCHITECTURE.md §9.3. Only identity/users holds the
private key and signs; every product validates locally with the public key, no network
call — what makes §9.2's 'no synchronous existence check' rule viable at all."""

import datetime

import jwt
import pydantic

from backend.commons.adapters import settings

_ALGORITHM = "RS256"
ACCESS_TOKEN_TTL = datetime.timedelta(minutes=15)


class AuthenticatedUser(pydantic.BaseModel):
    user_id: str


def issue_access_token(*, user_id: str) -> str:
    """Called only from identity/users/services/auth.py — the sole holder of the private
    key."""
    now = datetime.datetime.now(tz=datetime.UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.get_settings().jwt_private_key_pem, algorithm=_ALGORITHM)


def verify_access_token(token: str) -> AuthenticatedUser:
    key = settings.get_settings().jwt_public_key_pem
    payload = jwt.decode(token, key, algorithms=[_ALGORITHM])
    return AuthenticatedUser(user_id=payload["sub"])
