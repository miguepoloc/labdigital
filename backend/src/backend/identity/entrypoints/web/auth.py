"""`/v1/auth/*` y `/v1/.well-known/jwks.json` — contrato §2-§4.

Rutas públicas (sin access): register, verify-email, login, refresh, logout,
forgot-password, reset-password, resend-verification, verify, jwks. El resto exige la cookie
`ld_access`. Las mutaciones pasan además por `CsrfMiddleware`.
"""

import contextlib
from urllib import parse

import fastapi
from fastapi import responses, status
import pydantic

from backend.commons.adapters import authentication
from backend.commons.adapters.api import auth as api_auth
from backend.commons.adapters.api import exception_handler
from backend.commons.application import dto as base_dto
from backend.commons.domain import exceptions as commons_exceptions
from backend.identity.entrypoints.web import _dependencies
from backend.identity.services import dto as identity_dto
from backend.identity.services import (
    login_orchestrator,
    refresh_orchestrator,
    reset_password_orchestrator,
)
from backend.identity.sessions.domain.model import value_objects as sessions_value_objects
from backend.identity.sessions.services import dto as sessions_dto
from backend.identity.sessions.services import sessions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users

router = fastapi.APIRouter(prefix="/auth", tags=["auth"])
wellknown_router = fastapi.APIRouter(tags=["auth"])

_ACCEPTED_MESSAGE = (
    "Si los datos son correctos, te enviamos un correo con las instrucciones. "
    "Revisa tu bandeja de entrada."
)


class AcceptedOutputDTO(base_dto.BaseDTO):
    """Cuerpo idéntico de las respuestas 202 (no revela si el correo existe)."""

    message: str = _ACCEPTED_MESSAGE


class RegisterBody(base_dto.BaseDTO):
    email: str = pydantic.Field(max_length=320)
    full_name: str = pydantic.Field(max_length=200)
    password: str = pydantic.Field(max_length=1024)
    accept_data_policy: bool


class EmailBody(base_dto.BaseDTO):
    email: str = pydantic.Field(max_length=320)


class TokenBody(base_dto.BaseDTO):
    token: str = pydantic.Field(max_length=512)


class ResetPasswordBody(base_dto.BaseDTO):
    token: str = pydantic.Field(max_length=512)
    password: str = pydantic.Field(max_length=1024)


class LoginBody(base_dto.BaseDTO):
    email: str = pydantic.Field(max_length=320)
    password: str = pydantic.Field(max_length=1024)
    remember: bool = False


@router.post("/register", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedOutputDTO)
def register(
    body: RegisterBody,
    uow: _dependencies.UowDep,
    config: _dependencies.ConfigDep,
    context: _dependencies.ContextDep,
) -> AcceptedOutputDTO:
    users.register(
        uow=uow,
        input_dto=users_dto.RegisterInputDTO(**body.model_dump()),
        config=config,
        context=context,
    )
    return AcceptedOutputDTO()


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(
    body: TokenBody, uow: _dependencies.UowDep, config: _dependencies.ConfigDep
) -> fastapi.Response:
    users.verify_email(uow=uow, input_dto=users_dto.TokenInputDTO(token=body.token), config=config)
    return fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/resend-verification", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedOutputDTO
)
def resend_verification(
    body: EmailBody, uow: _dependencies.UowDep, config: _dependencies.ConfigDep
) -> AcceptedOutputDTO:
    users.resend_verification(
        uow=uow, input_dto=users_dto.EmailInputDTO(email=body.email), config=config
    )
    return AcceptedOutputDTO()


@router.post("/login", response_model=users_dto.MeOutputDTO)
def login(
    body: LoginBody,
    response: fastapi.Response,
    uow: _dependencies.UowDep,
    context: _dependencies.ContextDep,
) -> users_dto.MeOutputDTO:
    result = login_orchestrator.login(
        uow=uow,
        input_dto=identity_dto.LoginInputDTO(
            email=body.email, password=body.password, remember=body.remember
        ),
        context=context,
    )
    _dependencies.set_access_cookie(response, result.tokens.access_token)
    _dependencies.set_refresh_cookie(response, result.tokens.refresh)
    return result.me


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(
    request: fastapi.Request, uow: _dependencies.UowDep, context: _dependencies.ContextDep
) -> fastapi.Response:
    refresh_token = request.cookies.get(api_auth.REFRESH_COOKIE, "")
    try:
        tokens = refresh_orchestrator.refresh(uow=uow, refresh_token=refresh_token, context=context)
    except commons_exceptions.UnauthorizedError as error:
        failed = exception_handler.error_response(
            status_code=status.HTTP_401_UNAUTHORIZED, code=error.code, message=str(error)
        )
        _dependencies.clear_auth_cookies(failed)
        return failed
    response = fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)
    _dependencies.set_access_cookie(response, tokens.access_token)
    _dependencies.set_refresh_cookie(response, tokens.refresh)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: fastapi.Request, uow: _dependencies.UowDep) -> fastapi.Response:
    """Idempotente: revoca la sesión de la cookie de refresh (o, si no llega, la del `sid`
    del access) y borra ambas cookies."""
    refresh_token = request.cookies.get(api_auth.REFRESH_COOKIE)
    revoked = None
    if refresh_token:
        revoked = sessions.revoke_by_refresh_token(
            uow=uow,
            refresh_token=refresh_token,
            reason=sessions_value_objects.RevokeReason.LOGOUT,
        )
    claims = api_auth.claims_from_cookie(request)
    if revoked is None and claims is not None:
        with contextlib.suppress(commons_exceptions.NotFoundError):
            sessions.revoke_session(
                uow=uow,
                session_id=claims.session_id,
                owner_user_id=claims.user_id,
                reason=sessions_value_objects.RevokeReason.LOGOUT,
            )
    response = fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)
    _dependencies.clear_auth_cookies(response)
    return response


@router.post(
    "/forgot-password", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedOutputDTO
)
def forgot_password(
    body: EmailBody,
    uow: _dependencies.UowDep,
    config: _dependencies.ConfigDep,
    context: _dependencies.ContextDep,
) -> AcceptedOutputDTO:
    users.request_password_reset(
        uow=uow, input_dto=users_dto.EmailInputDTO(email=body.email), config=config, context=context
    )
    return AcceptedOutputDTO()


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    body: ResetPasswordBody, uow: _dependencies.UowDep, config: _dependencies.ConfigDep
) -> fastapi.Response:
    reset_password_orchestrator.reset_password(
        uow=uow,
        input_dto=users_dto.ResetPasswordInputDTO(token=body.token, password=body.password),
        config=config,
    )
    response = fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)
    _dependencies.clear_auth_cookies(response)
    return response


@router.get("/sessions", response_model=list[sessions_dto.SessionOutputDTO])
def list_sessions(
    claims: api_auth.ClaimsDep, uow: _dependencies.UowDep
) -> list[sessions_dto.SessionOutputDTO]:
    return sessions.list_active(
        uow=uow, user_id=claims.user_id, current_session_id=claims.session_id
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: str, claims: api_auth.ClaimsDep, uow: _dependencies.UowDep
) -> fastapi.Response:
    sessions.revoke_session(
        uow=uow,
        session_id=session_id,
        owner_user_id=claims.user_id,
        reason=sessions_value_objects.RevokeReason.REVOKED_BY_USER,
    )
    response = fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)
    if session_id == claims.session_id:
        _dependencies.clear_auth_cookies(response)
    return response


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(
    claims: api_auth.ClaimsDep, uow: _dependencies.UowDep
) -> fastapi.Response:
    sessions.revoke_all_for_user(
        uow=uow,
        user_id=claims.user_id,
        reason=sessions_value_objects.RevokeReason.REVOKED_OTHERS,
        keep_session_id=claims.session_id,
    )
    return fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"description": "Sin access válido"}},
)
def verify(request: fastapi.Request) -> fastapi.Response:
    """Para nginx `auth_request` (contrato §3). SIN BD: sólo valida el JWT de `ld_access`."""
    claims = api_auth.claims_from_cookie(request)
    if claims is None:
        return exception_handler.error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthenticated",
            message="Sesión no válida o caducada.",
        )
    return fastapi.Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "X-LabDigital-User": claims.user_id,
            "X-LabDigital-Email": claims.email,
            "X-LabDigital-Name": parse.quote(claims.name, safe=""),
            "X-LabDigital-Role": claims.role,
            "Cache-Control": "no-store",
        },
    )


@wellknown_router.get("/.well-known/jwks.json")
def jwks() -> responses.JSONResponse:
    return responses.JSONResponse(
        authentication.jwks(), headers={"Cache-Control": "public, max-age=300"}
    )
