"""FastAPI dependency wiring shared by public.py and internal.py — kept file-local
(prefixed `_`) since this exact composition (JWT vs. service-to-service auth as two
alternative FastAPI dependencies) is this product's own operational concern, even though
`INTERNAL_API_KEY` itself now lives in the shared `commons.adapters.settings.Settings`
(both this file's `require_service_auth` and `commerce.orders.adapters
.user_profile_adapter`'s caller need the same value — a cross-product concern, not a
product-local one, once traced through)."""

import hmac
from typing import Annotated

import fastapi
from fastapi import status
import fastapi.security

from backend.commons.adapters import authentication, settings, unit_of_work
from backend.identity.users.domain.model import value_objects

_bearer_scheme = fastapi.security.HTTPBearer()


def get_uow() -> unit_of_work.UnitOfWork:
    return unit_of_work.build()


def require_jwt(
    credentials: Annotated[
        fastapi.security.HTTPAuthorizationCredentials, fastapi.Depends(_bearer_scheme)
    ],
) -> value_objects.UserId:
    user = authentication.verify_access_token(credentials.credentials)
    return value_objects.UserId(value=user.user_id)


def require_service_auth(x_internal_api_key: Annotated[str, fastapi.Header()]) -> None:
    expected = settings.get_settings().internal_api_key
    if not hmac.compare_digest(x_internal_api_key, expected):
        raise fastapi.HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key."
        )
