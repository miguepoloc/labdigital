"""Integration test for `identity.users.services.auth` — ARCHITECTURE.md §15's `integration`
row: real PostgreSQL via testcontainers, the real `unit_of_work.UnitOfWork`, and the real
`DefaultUserRepository`/`adapters/refresh_tokens.py`. Covers exactly the slice
`tests/unit/backend/identity/users/test_auth.py` deliberately cannot reach: `login`'s happy
path, `refresh`, `deactivate_user`'s happy path, and `expire_refresh_tokens` — all of them
call `refresh_tokens.issue`/`redeem`/`revoke_all_for_user`/`expire_stale` directly on a real
SQLAlchemy `Session` (`uow.session`), with no port/seam a `FakeUnitOfWork` can stand in for.

Schema setup uses `Base.metadata.create_all`, not `alembic upgrade head`: this template's
`migrations/` directory has no version scripts yet (only the Alembic scaffold under
`migrations/env.py`/`script.py.mako`), and `migrations/env.py` itself calls
`settings.get_postgres_uri()` — a function that does not exist on
`commons.adapters.settings` (only `Settings.postgres_uri`, an instance property, and
`get_settings()`, which returns a `Settings` instance). That's a real bug in `migrations/
env.py` that would make `alembic upgrade head` fail today regardless of test setup — flagged
separately in this change's report, not fixed here (out of this task's `src/backend` scope
and not needed for this test, since ARCHITECTURE.md §15 explicitly allows
`Base.metadata.create_all` against the container as an alternative)."""

import os
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from testcontainers.postgres import PostgresContainer

from backend.commons.adapters import engine as engine_module
from backend.commons.adapters import orm_base, settings, unit_of_work
from backend.identity.users.adapters import orm as users_orm
from backend.identity.users.domain.model import exceptions
from backend.identity.users.services import auth, dto

pytestmark = pytest.mark.integration


def _generate_rsa_key_pair() -> tuple[str, str]:
    """`authentication.issue_access_token`/`verify_access_token` need a real RS256 key pair
    (ARCHITECTURE.md §9.3) — generated fresh per test run rather than a checked-in PEM, so
    nothing test-only ever risks being mistaken for a real credential."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


@pytest.fixture(scope="module")
def real_uow() -> Generator[unit_of_work.UnitOfWork]:
    private_key, public_key = _generate_rsa_key_pair()
    with PostgresContainer("postgres:16-alpine") as postgres:
        os.environ["APP_ENV"] = "test"
        os.environ["DB_HOST"] = postgres.get_container_host_ip()
        os.environ["DB_PORT"] = str(postgres.get_exposed_port(postgres.port))
        os.environ["DB_USER"] = postgres.username
        os.environ["DB_PASSWORD"] = postgres.password
        os.environ["DB_NAME"] = postgres.dbname
        os.environ["JWT_PRIVATE_KEY_PEM"] = private_key
        os.environ["JWT_PUBLIC_KEY_PEM"] = public_key
        os.environ["INTERNAL_API_KEY"] = "test-internal-api-key"
        os.environ["PRICING_SERVICE_BASE_URL"] = "http://localhost:9000"
        os.environ["IDENTITY_INTERNAL_API_BASE_URL"] = "http://localhost:8001"

        # These three are cached module-level singletons (ARCHITECTURE.md §14.1) — reset
        # them so this test's env vars actually take effect instead of an earlier, unrelated
        # get_settings()/get_engine() call in the same process winning.
        settings._SETTINGS = None
        engine_module._engine = None
        engine_module._session_factory = None

        sa_engine = engine_module.get_engine()
        orm_base.Base.metadata.create_all(sa_engine)

        yield unit_of_work.UnitOfWork()

        orm_base.Base.metadata.drop_all(sa_engine)
        sa_engine.dispose()
        settings._SETTINGS = None
        engine_module._engine = None
        engine_module._session_factory = None


def test_register_login_refresh_deactivate_flow(real_uow: unit_of_work.UnitOfWork) -> None:
    registered = auth.register_user(
        uow=real_uow,
        input_dto=dto.RegisterUserInputDTO(
            email="ada@example.com", full_name="Ada Lovelace", password="correct-horse-battery-staple"
        ),
    )
    assert registered.email == "ada@example.com"
    assert registered.is_active is True

    tokens = auth.login(
        uow=real_uow,
        input_dto=dto.LoginInputDTO(email="ada@example.com", password="correct-horse-battery-staple"),
    )
    assert tokens.access_token
    assert tokens.refresh_token

    refreshed = auth.refresh(uow=real_uow, input_dto=dto.RefreshInputDTO(refresh_token=tokens.refresh_token))
    assert refreshed.access_token
    assert refreshed.refresh_token != tokens.refresh_token  # each refresh rotates the token

    deactivated = auth.deactivate_user(
        uow=real_uow, input_dto=dto.DeactivateUserInputDTO(user_id=registered.id)
    )
    assert deactivated.is_active is False

    # A deactivated user can no longer log in, and their prior sessions were revoked by
    # deactivate_user's own refresh_tokens.revoke_all_for_user call.
    with pytest.raises(exceptions.InvalidCredentialsError):
        auth.login(
            uow=real_uow,
            input_dto=dto.LoginInputDTO(email="ada@example.com", password="correct-horse-battery-staple"),
        )
    with pytest.raises(exceptions.RefreshTokenNotFoundError):
        auth.refresh(uow=real_uow, input_dto=dto.RefreshInputDTO(refresh_token=refreshed.refresh_token))


def test_expire_refresh_tokens_deletes_only_stale_rows(real_uow: unit_of_work.UnitOfWork) -> None:
    registered = auth.register_user(
        uow=real_uow,
        input_dto=dto.RegisterUserInputDTO(
            email="grace@example.com", full_name="Grace Hopper", password="another-strong-password"
        ),
    )
    with real_uow.transaction():
        real_uow.session.add(
            users_orm.RefreshTokenOrm(
                id=uuid.uuid4(),
                user_id=registered.id,
                token_hash="deadbeef",
                expires_at=0,  # long expired, well past expire_stale's one-day grace window
                revoked_at=None,
                created_at=0,
                updated_at=0,
            )
        )

    expired_count = auth.expire_refresh_tokens(uow=real_uow)

    assert expired_count == 1
    with real_uow.transaction():
        # Scoped to this user's own rows, not the whole table — the earlier flow test's
        # user (sharing this module-scoped container) still has its own, non-stale tokens.
        remaining_for_grace = real_uow.session.execute(
            sa.select(sa.func.count())
            .select_from(users_orm.RefreshTokenOrm)
            .where(users_orm.RefreshTokenOrm.user_id == registered.id)
        ).scalar_one()
    assert remaining_for_grace == 0
