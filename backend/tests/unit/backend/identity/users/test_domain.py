import datetime

import argon2
import pytest
import time_machine

from backend.commons.domain import exceptions as commons_exceptions
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.users.domain.model import aggregate, exceptions, rules, value_objects

pytestmark = pytest.mark.unit


def _user(email: str = "ada@example.com") -> aggregate.User:
    return aggregate.User.register(
        email=value_objects.Email(value=email),
        full_name=value_objects.FullName(value="Ada Lovelace"),
        plaintext_password="caballo-bateria-grapa",
        data_policy_version="acuerdo-17-2018",
    )


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("corta", "too_short"),
        ("1234567890", "too_common"),
        ("Contraseña123", "too_common"),
        ("aaaaaaaaaaaa", "too_common"),
        ("x" * 300, "too_long"),
    ],
)
def test_password_policy_rejects(password: str, reason: str) -> None:
    with pytest.raises(commons_exceptions.ValidationError) as info:
        rules.PasswordPolicy(password).check()
    assert info.value.details["reason"] == reason


def test_password_policy_accepts_reasonable_password() -> None:
    rules.PasswordPolicy("caballo-bateria-grapa").check()


def test_email_is_normalized_and_validated() -> None:
    assert value_objects.Email(value="  Ada@Example.COM ").value == "ada@example.com"
    with pytest.raises(commons_exceptions.ValidationError):
        value_objects.Email(value="no-es-correo")


def test_hashed_password_is_argon2id_and_verifies() -> None:
    hashed = value_objects.HashedPassword.hash_plaintext("caballo-bateria-grapa")
    assert hashed.encoded.startswith("$argon2id$")
    assert hashed.matches("caballo-bateria-grapa")
    assert not hashed.matches("otra-cosa-distinta")
    assert not value_objects.HashedPassword(encoded="basura").matches("x")


def test_rehash_is_transparent_when_parameters_change(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user()
    old_hash = user.hashed_password.encoded
    monkeypatch.setattr(
        value_objects, "_HASHER", argon2.PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
    )
    assert user.verify_password("caballo-bateria-grapa")  # el hash viejo sigue verificando
    assert user.rehash_password_if_needed("caballo-bateria-grapa")
    assert user.hashed_password.encoded != old_hash
    assert "t=2" in user.hashed_password.encoded
    assert user.credentials_version == 1  # mismo secreto: no invalida sesiones
    assert not user.rehash_password_if_needed("caballo-bateria-grapa")


def test_verify_email_promotes_admin_emails_only() -> None:
    admin = _user("admin@example.com")
    assert (
        admin.verify_email(admin_emails=frozenset({"admin@example.com"}))
        is identity_value_objects.Role.USER
    )
    assert admin.role is identity_value_objects.Role.ADMIN and admin.is_email_verified

    regular = _user()
    assert regular.verify_email(admin_emails=frozenset({"admin@example.com"})) is None
    assert regular.role is identity_value_objects.Role.USER


def test_change_password_bumps_credentials_version_and_checks_policy() -> None:
    user = _user()
    user.change_password("otra-contrasena-larga")
    assert user.credentials_version == 2
    assert user.verify_password("otra-contrasena-larga")
    with pytest.raises(commons_exceptions.ValidationError):
        user.change_password("corta")


def test_ensure_can_log_in() -> None:
    user = _user()
    with pytest.raises(exceptions.EmailNotVerifiedError):
        user.ensure_can_log_in()
    user.verify_email(admin_emails=frozenset())
    user.ensure_can_log_in()
    user.deactivate()
    with pytest.raises(exceptions.AccountInactiveError):
        user.ensure_can_log_in()


def test_email_token_single_use_and_expiry() -> None:
    user = _user()
    token, secret = aggregate.EmailToken.issue(
        user_id=user.id, purpose=value_objects.EmailTokenPurpose.PASSWORD_RESET
    )
    assert token.token_hash == value_objects.hash_token_secret(secret)
    assert secret not in token.token_hash
    token.consume()
    with pytest.raises(exceptions.InvalidEmailTokenError):
        token.consume()

    fresh, _ = aggregate.EmailToken.issue(
        user_id=user.id, purpose=value_objects.EmailTokenPurpose.PASSWORD_RESET
    )
    with (
        time_machine.travel(
            datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(minutes=31)
        ),
        pytest.raises(exceptions.InvalidEmailTokenError),
    ):
        fresh.consume()
