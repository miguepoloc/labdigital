"""Unit tests for `identity.users.services.auth` — ARCHITECTURE.md §15. Fakes only, no
Postgres. Covers exactly the slice of `auth.py` that never reaches `uow.session` (verified by
reading each function body first): `register_user`, `login`'s three failure paths,
`get_user_profile`, and `deactivate_user`'s failure path only. `login`'s happy path,
`refresh`, `expire_refresh_tokens`, and `deactivate_user`'s happy path all call
`adapters/refresh_tokens.py` functions that take a real SQLAlchemy `Session` directly — those
are covered by `tests/integration/backend/identity/users/test_auth_integration.py` instead."""

from typing import Any

import pytest

from backend.commons.domain import aggregates
from backend.identity.users.domain.model import aggregate, exceptions, value_objects
from backend.identity.users.services import auth, dto
from tests.unit import fakes
from tests.unit.backend.identity.users import fakes as user_fakes

pytestmark = pytest.mark.unit

_EMAIL = "ada@example.com"
_PASSWORD = "correct-horse-battery-staple"


def _build_uow() -> tuple[fakes.FakeUnitOfWork, user_fakes.FakeUserRepository]:
    repos: dict[type[aggregates.AggregateRoot[Any]], Any] = {}
    uow = fakes.FakeUnitOfWork(repos=repos)
    user_repo = user_fakes.FakeUserRepository(outbox=uow.outbox)
    repos[aggregate.User] = user_repo
    return uow, user_repo


def _register(uow: fakes.FakeUnitOfWork, *, email: str = _EMAIL, password: str = _PASSWORD) -> dto.UserOutputDTO:
    return auth.register_user(
        uow=uow,
        input_dto=dto.RegisterUserInputDTO(email=email, full_name="Ada Lovelace", password=password),
    )


def test_register_user_success() -> None:
    uow, _ = _build_uow()

    registered = _register(uow)

    assert registered.email == _EMAIL
    assert registered.is_active is True
    assert uow.outbox.recorded  # UserRegistered drained through the fake repo's add()
    assert uow.audit.entries


def test_register_user_duplicate_email_raises() -> None:
    uow, _ = _build_uow()
    _register(uow)

    with pytest.raises(exceptions.UserAlreadyExistsError):
        _register(uow)


def test_login_user_not_found_raises_invalid_credentials() -> None:
    uow, _ = _build_uow()

    with pytest.raises(exceptions.InvalidCredentialsError):
        auth.login(uow=uow, input_dto=dto.LoginInputDTO(email="missing@example.com", password="whatever"))


def test_login_wrong_password_raises_invalid_credentials() -> None:
    uow, _ = _build_uow()
    _register(uow)

    with pytest.raises(exceptions.InvalidCredentialsError):
        auth.login(uow=uow, input_dto=dto.LoginInputDTO(email=_EMAIL, password="wrong-password"))


def test_login_inactive_user_raises_invalid_credentials() -> None:
    uow, user_repo = _build_uow()
    _register(uow)
    user = user_repo.get_by_email(value_objects.Email(value=_EMAIL))
    user.deactivate()
    user_repo.update(user)  # bypasses deactivate_user's own uow.session-touching call — this
    # test only needs the User aggregate itself to be inactive before login runs.

    with pytest.raises(exceptions.InvalidCredentialsError):
        auth.login(uow=uow, input_dto=dto.LoginInputDTO(email=_EMAIL, password=_PASSWORD))


def test_get_user_profile_success() -> None:
    uow, _ = _build_uow()
    registered = _register(uow)

    profile = auth.get_user_profile(uow=uow, user_id=value_objects.UserId(value=registered.id))

    assert profile.email == _EMAIL
    assert profile.full_name == "Ada Lovelace"


def test_get_user_profile_not_found_raises() -> None:
    uow, _ = _build_uow()

    with pytest.raises(exceptions.UserNotFoundError):
        auth.get_user_profile(uow=uow, user_id=value_objects.UserId.new())


def test_deactivate_user_not_found_raises() -> None:
    uow, _ = _build_uow()

    with pytest.raises(exceptions.UserNotFoundError):
        auth.deactivate_user(
            uow=uow, input_dto=dto.DeactivateUserInputDTO(user_id=value_objects.UserId.new().value)
        )
