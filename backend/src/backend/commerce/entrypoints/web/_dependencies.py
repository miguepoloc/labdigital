"""FastAPI dependency wiring for commerce's entrypoints. `require_jwt` reuses
commons.adapters.authentication directly — verification is stateless and product-agnostic
(ARCHITECTURE.md §9.3: any product verifies locally, no network call back to identity)."""

from typing import Annotated

import fastapi
import fastapi.security

from backend.commons.adapters import authentication, unit_of_work

_bearer_scheme = fastapi.security.HTTPBearer()


def get_uow() -> unit_of_work.UnitOfWork:
    return unit_of_work.build()


def require_jwt(
    credentials: Annotated[
        fastapi.security.HTTPAuthorizationCredentials, fastapi.Depends(_bearer_scheme)
    ],
) -> authentication.AuthenticatedUser:
    return authentication.verify_access_token(credentials.credentials)
