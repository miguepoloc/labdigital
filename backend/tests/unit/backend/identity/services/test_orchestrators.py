import pytest

from backend.commons.adapters import authentication
from backend.identity.services import (
    dto,
    login_orchestrator,
    refresh_orchestrator,
    reset_password_orchestrator,
)
from backend.identity.sessions.domain.model import exceptions as sessions_exceptions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users
from tests import helpers
from tests.unit.backend.identity import builders

pytestmark = pytest.mark.unit

_EMAIL = "grace@example.com"
_PASSWORD = "caballo-bateria-grapa"


def _verified_user(f: builders.IdentityFakes) -> None:
    users.register(
        uow=f.uow,  # type: ignore[arg-type]
        input_dto=users_dto.RegisterInputDTO(
            email=_EMAIL, full_name="Grace Hopper", password=_PASSWORD, accept_data_policy=True
        ),
        config=builders.CONFIG,
        context=builders.CONTEXT,
    )
    message = helpers.email_events(f.uow.outbox.recorded, category="verify_email")[-1].message
    users.verify_email(
        uow=f.uow,
        input_dto=users_dto.TokenInputDTO(token=helpers.token_from_message(message)),
        config=builders.CONFIG,
    )  # type: ignore[arg-type]


def _login(f: builders.IdentityFakes) -> dto.LoginOutputDTO:
    return login_orchestrator.login(
        uow=f.uow,  # type: ignore[arg-type]
        input_dto=dto.LoginInputDTO(email=_EMAIL, password=_PASSWORD, remember=True),
        context=builders.CONTEXT,
    )


def test_login_issues_access_with_contract_claims() -> None:
    f = builders.build()
    _verified_user(f)
    result = _login(f)
    claims = authentication.verify_access_token(result.tokens.access_token)
    assert claims.user_id == result.me.id
    assert claims.session_id == result.tokens.refresh.session_id
    assert (claims.role, claims.credentials_version, claims.email, claims.name) == (
        "user",
        1,
        _EMAIL,
        "Grace Hopper",
    )


def test_refresh_rotates_and_reset_password_revokes_all_sessions() -> None:
    f = builders.build()
    _verified_user(f)
    one, two = _login(f), _login(f)
    rotated = refresh_orchestrator.refresh(
        uow=f.uow, refresh_token=one.tokens.refresh.refresh_token, context=builders.CONTEXT
    )  # type: ignore[arg-type]
    assert rotated.refresh.refresh_token != one.tokens.refresh.refresh_token

    users.request_password_reset(
        uow=f.uow,
        input_dto=users_dto.EmailInputDTO(email=_EMAIL),
        config=builders.CONFIG,
        context=builders.CONTEXT,
    )  # type: ignore[arg-type]
    message = helpers.email_events(f.uow.outbox.recorded, category="password_reset")[-1].message
    reset_password_orchestrator.reset_password(
        uow=f.uow,  # type: ignore[arg-type]
        input_dto=users_dto.ResetPasswordInputDTO(
            token=helpers.token_from_message(message), password="otra-contrasena-nueva"
        ),
        config=builders.CONFIG,
    )

    for token in (rotated.refresh.refresh_token, two.tokens.refresh.refresh_token):
        with pytest.raises(sessions_exceptions.RefreshTokenInvalidError):
            refresh_orchestrator.refresh(uow=f.uow, refresh_token=token, context=builders.CONTEXT)  # type: ignore[arg-type]
