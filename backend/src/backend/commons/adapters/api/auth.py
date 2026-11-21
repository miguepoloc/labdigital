"""Autenticación en la capa web, compartida por todos los contextos (contrato §2).

El access viaja SOLO en la cookie `ld_access` (HttpOnly) y se valida localmente con la
clave pública: sin BD. `require_claims` es la dependencia FastAPI de cualquier ruta privada.
"""

from typing import Annotated

import fastapi

from backend.commons.adapters import authentication
from backend.commons.domain import exceptions

ACCESS_COOKIE = "ld_access"
REFRESH_COOKIE = "ld_refresh"
# Indicador NO HttpOnly (contrato §6.1): sólo dice a la SPA que hay sesión; nunca autoriza.
SESSION_COOKIE = "ld_session"


class NotAuthenticatedError(exceptions.UnauthorizedError):
    def __init__(self) -> None:
        super().__init__("Sesión no válida o caducada.", code="unauthenticated")


def claims_from_cookie(request: fastapi.Request) -> authentication.AccessClaims | None:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    try:
        return authentication.verify_access_token(token)
    except authentication.InvalidAccessTokenError:
        return None


def require_claims(request: fastapi.Request) -> authentication.AccessClaims:
    claims = claims_from_cookie(request)
    if claims is None:
        raise NotAuthenticatedError()
    return claims


ClaimsDep = Annotated[authentication.AccessClaims, fastapi.Depends(require_claims)]
