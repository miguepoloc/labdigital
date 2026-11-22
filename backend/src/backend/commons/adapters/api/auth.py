"""Autenticación en la capa web, compartida por todos los contextos (contrato §2).

El access viaja SOLO en la cookie `ld_access` (HttpOnly) y se valida con la clave pública.
`require_claims` es la dependencia FastAPI de cualquier ruta privada y, además de la firma,
comprueba en BD que la sesión `sid` sigue viva y que `ver` coincide (`register_liveness_check`,
que cablea la raíz de composición con `identity`): así un access robado deja de valer en
cuanto se cierra la sesión, se revoca o se desactiva al usuario, sin esperar sus 15 min.
`GET /auth/verify` (nginx) usa `claims_from_cookie` y sigue SIN BD, como fija el contrato §3.
"""

from collections.abc import Callable
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


LivenessCheck = Callable[[authentication.AccessClaims], bool]
_liveness_check: LivenessCheck | None = None


def register_liveness_check(check: LivenessCheck) -> None:
    """La llama una vez la raíz de composición web (commons no conoce `identity`)."""
    global _liveness_check
    _liveness_check = check


def require_claims(request: fastapi.Request) -> authentication.AccessClaims:
    claims = claims_from_cookie(request)
    if claims is None:
        raise NotAuthenticatedError()
    if _liveness_check is None:  # cerrado ante un fallo de cableado, nunca abierto
        raise RuntimeError("Comprobación de sesión sin registrar (ver entrypoints.web.app).")
    if not _liveness_check(claims):
        raise NotAuthenticatedError()
    return claims


ClaimsDep = Annotated[authentication.AccessClaims, fastapi.Depends(require_claims)]
