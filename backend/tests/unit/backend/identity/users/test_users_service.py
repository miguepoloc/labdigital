import pytest

from backend.commons.domain import exceptions as commons_exceptions
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.users.domain.model import exceptions, value_objects
from backend.identity.users.services import dto, users
from tests import helpers
from tests.unit.backend.identity import builders

pytestmark = pytest.mark.unit

_EMAIL = "ada@example.com"
_PASSWORD = "caballo-bateria-grapa"


def _register(f: builders.IdentityFakes, *, email: str = _EMAIL, ip: str = "10.0.0.1") -> None:
    users.register(
        uow=f.uow,  # type: ignore[arg-type]
        input_dto=dto.RegisterInputDTO(
            email=email, full_name="Ada Lovelace", password=_PASSWORD, accept_data_policy=True
        ),
        config=builders.CONFIG,
        context=dto.RequestContext(ip=ip),
    )


def _verify_latest(f: builders.IdentityFakes, email: str = _EMAIL) -> None:
    message = helpers.email_events(f.uow.outbox.recorded, to=email, category="verify_email")[
        -1
    ].message
    users.verify_email(
        uow=f.uow,  # type: ignore[arg-type]
        input_dto=dto.TokenInputDTO(token=helpers.token_from_message(message)),
        config=builders.CONFIG,
    )


def _login(
    f: builders.IdentityFakes, password: str = _PASSWORD, email: str = _EMAIL
) -> dto.AuthenticatedUserOutputDTO:
    return users.authenticate(
        uow=f.uow,  # type: ignore[arg-type]
        input_dto=dto.LoginInputDTO(email=email, password=password),
        context=builders.CONTEXT,
    )


def test_register_creates_user_records_policy_and_sends_verification() -> None:
    f = builders.build()
    _register(f)

    (user,) = f.users.by_id.values()
    assert user.data_policy.version == "2026-11"
    assert not user.is_email_verified
    (event,) = helpers.email_events(f.uow.outbox.recorded, category="verify_email")
    assert event.message.to == _EMAIL
    assert "https://testserver/labdigital/verificar?t=" in event.message.text
    assert "registered" in f.uow.audit.actions()


def test_register_existing_email_is_silent_and_does_not_duplicate() -> None:
    f = builders.build()
    _register(f)
    _verify_latest(f)

    _register(f)  # no lanza: la respuesta HTTP será idéntica

    assert len(f.users.by_id) == 1
    assert helpers.email_events(f.uow.outbox.recorded, category="already_registered")


def test_register_requires_data_policy() -> None:
    f = builders.build()
    with pytest.raises(exceptions.DataPolicyNotAcceptedError):
        users.register(
            uow=f.uow,  # type: ignore[arg-type]
            input_dto=dto.RegisterInputDTO(
                email=_EMAIL, full_name="Ada", password=_PASSWORD, accept_data_policy=False
            ),
            config=builders.CONFIG,
            context=builders.CONTEXT,
        )


def test_register_rate_limited_per_ip() -> None:
    f = builders.build()
    for i in range(10):
        _register(f, email=f"u{i}@example.com", ip="1.2.3.4")
    with pytest.raises(commons_exceptions.TooManyRequestsError):
        _register(f, email="otro@example.com", ip="1.2.3.4")
    _register(f, email="otro@example.com", ip="5.6.7.8")


def test_verify_email_then_login_and_admin_promotion() -> None:
    f = builders.build()
    _register(f, email="admin@example.com")
    _verify_latest(f, "admin@example.com")

    result = _login(f, email="admin@example.com")

    assert result.me.email_verified and result.me.role == "admin"
    assert "role_changed" in f.uow.audit.actions()
    assert "login_succeeded" in f.uow.audit.actions()


def test_verify_email_token_is_single_use() -> None:
    f = builders.build()
    _register(f)
    message = helpers.email_events(f.uow.outbox.recorded, category="verify_email")[-1].message
    token = helpers.token_from_message(message)
    users.verify_email(uow=f.uow, input_dto=dto.TokenInputDTO(token=token), config=builders.CONFIG)  # type: ignore[arg-type]
    with pytest.raises(exceptions.InvalidEmailTokenError):
        users.verify_email(
            uow=f.uow, input_dto=dto.TokenInputDTO(token=token), config=builders.CONFIG
        )  # type: ignore[arg-type]


def test_login_errors() -> None:
    f = builders.build()
    _register(f)
    with pytest.raises(exceptions.EmailNotVerifiedError):
        _login(f)
    _verify_latest(f)
    with pytest.raises(exceptions.InvalidCredentialsError):
        _login(f, password="contrasena-incorrecta")
    assert "login_failed" in f.uow.audit.actions()
    with pytest.raises(exceptions.InvalidCredentialsError):
        _login(f, email="nadie@example.com")


def test_login_rate_limited_per_ip_and_email() -> None:
    f = builders.build()
    for _ in range(5):
        with pytest.raises(exceptions.InvalidCredentialsError):
            _login(f, email="nadie@example.com")
    with pytest.raises(commons_exceptions.TooManyRequestsError):
        _login(f, email="nadie@example.com")


def test_forgot_password_is_silent_for_unknown_and_rate_limited() -> None:
    f = builders.build()
    request = dto.EmailInputDTO(email="nadie@example.com")
    for _ in range(3):
        users.request_password_reset(
            uow=f.uow, input_dto=request, config=builders.CONFIG, context=builders.CONTEXT
        )  # type: ignore[arg-type]
    assert not helpers.email_events(f.uow.outbox.recorded)
    with pytest.raises(commons_exceptions.TooManyRequestsError):
        users.request_password_reset(
            uow=f.uow, input_dto=request, config=builders.CONFIG, context=builders.CONTEXT
        )  # type: ignore[arg-type]


def test_reset_password_changes_password_and_bumps_version() -> None:
    f = builders.build()
    _register(f)
    _verify_latest(f)
    users.request_password_reset(
        uow=f.uow,
        input_dto=dto.EmailInputDTO(email=_EMAIL),
        config=builders.CONFIG,
        context=builders.CONTEXT,
    )  # type: ignore[arg-type]
    message = helpers.email_events(f.uow.outbox.recorded, category="password_reset")[-1].message
    assert "/restablecer?t=" in message.text and "30 minutos" in message.text
    token = helpers.token_from_message(message)

    claims = users.reset_password(
        uow=f.uow,  # type: ignore[arg-type]
        input_dto=dto.ResetPasswordInputDTO(token=token, password="nueva-contrasena-segura"),
        config=builders.CONFIG,
    )

    assert claims.credentials_version == 2
    _login(f, password="nueva-contrasena-segura")
    with pytest.raises(exceptions.InvalidEmailTokenError):
        users.reset_password(
            uow=f.uow,  # type: ignore[arg-type]
            input_dto=dto.ResetPasswordInputDTO(token=token, password="otra-contrasena-mas"),
            config=builders.CONFIG,
        )


def test_get_me_rejects_stale_credentials_version() -> None:
    f = builders.build()
    _register(f)
    (user,) = f.users.by_id.values()
    me = users.get_me(uow=f.uow, user_id=str(user.id), credentials_version=1)  # type: ignore[arg-type]
    assert me.email == _EMAIL and me.role == identity_value_objects.Role.USER
    with pytest.raises(exceptions.StaleCredentialsError):
        users.get_me(uow=f.uow, user_id=str(user.id), credentials_version=2)  # type: ignore[arg-type]


def test_change_password_requires_current() -> None:
    f = builders.build()
    _register(f)
    (user,) = f.users.by_id.values()
    with pytest.raises(exceptions.CurrentPasswordMismatchError):
        users.change_password(
            uow=f.uow,
            user_id=str(user.id),
            input_dto=dto.ChangePasswordInputDTO(
                current="mala-mala-mala", new="nueva-contrasena-segura"
            ),
        )  # type: ignore[arg-type]
    claims = users.change_password(
        uow=f.uow,
        user_id=str(user.id),
        input_dto=dto.ChangePasswordInputDTO(current=_PASSWORD, new="nueva-contrasena-segura"),
    )  # type: ignore[arg-type]
    assert claims.credentials_version == 2
    assert value_objects.Email(value=_EMAIL) == f.users.get(user.id).email
