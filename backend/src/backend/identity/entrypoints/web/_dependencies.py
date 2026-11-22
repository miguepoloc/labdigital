"""Raíz de composición web de `identity`: UoW por petición, configuración desde
`Settings`, contexto de la petición y cookies con los flags EXACTOS del contrato §2."""

from typing import Annotated

import fastapi

from backend.commons.adapters import authentication, settings, unit_of_work
from backend.commons.adapters.api import auth as api_auth
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.sessions.services import dto as sessions_dto
from backend.identity.users.services import dto as users_dto


def get_uow() -> unit_of_work.UnitOfWork:
    return unit_of_work.build()


def get_users_config() -> users_dto.UsersConfig:
    app_settings = settings.get_settings()
    return users_dto.UsersConfig(
        public_base_url=app_settings.public_base_url.rstrip("/"),
        admin_emails=app_settings.admin_email_set,
        data_policy_version=app_settings.data_policy_version,
    )


def get_request_context(request: fastapi.Request) -> users_dto.RequestContext:
    """`request.client.host` ya es la IP real si uvicorn corre con `--proxy-headers`
    (ver Dockerfile); nunca se lee `X-Forwarded-For` a mano."""
    ip = request.client.host if request.client else "desconocida"
    return users_dto.RequestContext(ip=ip, user_agent=request.headers.get("user-agent", ""))


UowDep = Annotated[unit_of_work.UnitOfWork, fastapi.Depends(get_uow)]
ConfigDep = Annotated[users_dto.UsersConfig, fastapi.Depends(get_users_config)]
ContextDep = Annotated[users_dto.RequestContext, fastapi.Depends(get_request_context)]


def _access_path() -> str:
    return f"{settings.get_settings().public_path_prefix}/"


def _refresh_path() -> str:
    return f"{settings.get_settings().public_path_prefix}/api/v1/auth/"


def set_access_cookie(response: fastapi.Response, access_token: str) -> None:
    """`ld_access`: HttpOnly; Secure; SameSite=Lax; Path=/labdigital/; 15 min."""
    response.set_cookie(
        api_auth.ACCESS_COOKIE,
        access_token,
        max_age=int(authentication.ACCESS_TOKEN_TTL.total_seconds()),
        path=_access_path(),
        secure=settings.get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )


def set_refresh_cookie(
    response: fastapi.Response, issued: sessions_dto.IssuedRefreshOutputDTO
) -> None:
    """`ld_refresh`: HttpOnly; Secure; SameSite=Strict; Path=/labdigital/api/v1/auth/;
    30 días, o cookie de sesión (sin Max-Age) si `remember=false`."""
    max_age: int | None = None
    if issued.persistent:
        now = base_value_objects.PosixTime.now().microseconds
        max_age = max(0, (issued.refresh_expires_at_microseconds - now) // 1_000_000)
    response.set_cookie(
        api_auth.REFRESH_COOKIE,
        issued.refresh_token,
        max_age=max_age,
        path=_refresh_path(),
        secure=settings.get_settings().cookie_secure,
        httponly=True,
        samesite="strict",
    )
    set_session_indicator_cookie(response, max_age=max_age)


def set_session_indicator_cookie(response: fastapi.Response, *, max_age: int | None) -> None:
    """`ld_session=1`: NO HttpOnly (la SPA la lee para no pedir `/me` sin sesión), Secure,
    SameSite=Lax, Path=/labdigital/, misma vida que `ld_refresh` (contrato §6.1). Jamás se
    usa para autorizar: la autorización es sólo `ld_access`."""
    response.set_cookie(
        api_auth.SESSION_COOKIE,
        "1",
        max_age=max_age,
        path=_access_path(),
        secure=settings.get_settings().cookie_secure,
        httponly=False,
        samesite="lax",
    )


def clear_auth_cookies(response: fastapi.Response) -> None:
    secure = settings.get_settings().cookie_secure
    response.delete_cookie(
        api_auth.ACCESS_COOKIE, path=_access_path(), secure=secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        api_auth.REFRESH_COOKIE,
        path=_refresh_path(),
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        api_auth.SESSION_COOKIE, path=_access_path(), secure=secure, httponly=False, samesite="lax"
    )
