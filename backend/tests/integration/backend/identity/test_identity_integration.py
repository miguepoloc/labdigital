"""Integración con Postgres real: servicios + repositorios + UoW + outbox + worker."""

import datetime

import pytest
import sqlalchemy as sa
import time_machine

from backend.commons.adapters import orm_base, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.entrypoints.worker import main as worker
from backend.identity.services import (
    dto,
    login_orchestrator,
    refresh_orchestrator,
    reset_password_orchestrator,
)
from backend.identity.sessions.adapters import orm as sessions_orm
from backend.identity.sessions.domain.model import exceptions as sessions_exceptions
from backend.identity.users.adapters import orm as users_orm
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users
from tests import capturing, helpers
from tests.unit.backend.identity import builders

pytestmark = pytest.mark.integration

_EMAIL = "linus@example.com"
_PASSWORD = "caballo-bateria-grapa"


def _register_and_verify(uow: unit_of_work.UnitOfWork, mailer: capturing.CapturingMailer) -> None:
    users.register(
        uow=uow,
        input_dto=users_dto.RegisterInputDTO(
            email=_EMAIL, full_name="Linus", password=_PASSWORD, accept_data_policy=True
        ),
        config=builders.CONFIG,
        context=builders.CONTEXT,
    )
    worker.run_once(uow, worker.build_handlers(mailer))
    token = helpers.token_from_message(mailer.to(_EMAIL)[-1])
    users.verify_email(
        uow=uow, input_dto=users_dto.TokenInputDTO(token=token), config=builders.CONFIG
    )


def _login(uow: unit_of_work.UnitOfWork) -> dto.LoginOutputDTO:
    return login_orchestrator.login(
        uow=uow,
        input_dto=dto.LoginInputDTO(email=_EMAIL, password=_PASSWORD, remember=True),
        context=builders.CONTEXT,
    )


def test_outbox_worker_sends_and_scrubs_token_from_payload(db: sa.Engine) -> None:
    uow, mailer = unit_of_work.build(), capturing.CapturingMailer()
    users.register(
        uow=uow,
        input_dto=users_dto.RegisterInputDTO(
            email=_EMAIL, full_name="Linus", password=_PASSWORD, accept_data_policy=True
        ),
        config=builders.CONFIG,
        context=builders.CONTEXT,
    )
    mailer.fail_next = 1
    worker.run_once(uow, worker.build_handlers(mailer))
    assert mailer.sent == []  # primer intento falla y queda programado el reintento
    with db.begin() as conn:
        conn.execute(sa.update(orm_base.OutboxEventOrm).values(next_attempt_at=0))
    worker.run_once(uow, worker.build_handlers(mailer))

    (message,) = mailer.to(_EMAIL)
    token = helpers.token_from_message(message)
    with db.connect() as conn:
        payloads = [
            row.payload
            for row in conn.execute(
                sa.select(orm_base.OutboxEventOrm).where(
                    orm_base.OutboxEventOrm.event_type == "EmailRequested"
                )
            )
        ]
        stored_hash = conn.execute(sa.select(users_orm.EmailTokenOrm.token_hash)).scalar_one()
    assert len(payloads) == 1 and payloads[0]["message"]["scrubbed"] is True
    assert token not in str(payloads) and token not in stored_hash


def test_rotation_and_reuse_revokes_family_in_db(db: sa.Engine) -> None:
    uow, mailer = unit_of_work.build(), capturing.CapturingMailer()
    _register_and_verify(uow, mailer)
    login = _login(uow)
    first = login.tokens.refresh.refresh_token
    second = refresh_orchestrator.refresh(
        uow=uow, refresh_token=first, context=builders.CONTEXT
    ).refresh.refresh_token

    with (
        time_machine.travel(_after_grace()),
        pytest.raises(sessions_exceptions.RefreshTokenInvalidError),
    ):
        refresh_orchestrator.refresh(uow=uow, refresh_token=first, context=builders.CONTEXT)
    with pytest.raises(sessions_exceptions.RefreshTokenInvalidError):
        refresh_orchestrator.refresh(uow=uow, refresh_token=second, context=builders.CONTEXT)

    with db.connect() as conn:
        session_row = conn.execute(sa.select(sessions_orm.SessionOrm)).one()
        tokens = conn.execute(sa.select(sessions_orm.RefreshTokenOrm)).all()
        audit_actions = conn.execute(sa.select(orm_base.AuditLogOrm.action)).scalars().all()
    assert session_row.revoke_reason == "refresh_reuse"
    assert len(tokens) == 2 and all(t.revoked_at is not None for t in tokens)
    assert {"login_succeeded", "refresh_reuse_detected", "email_verified"} <= set(audit_actions)


def test_concurrent_refresh_within_grace_does_not_revoke_family(db: sa.Engine) -> None:
    uow, mailer = unit_of_work.build(), capturing.CapturingMailer()
    _register_and_verify(uow, mailer)
    first = _login(uow).tokens.refresh.refresh_token
    tab_a = refresh_orchestrator.refresh(uow=uow, refresh_token=first, context=builders.CONTEXT)
    tab_b = refresh_orchestrator.refresh(uow=uow, refresh_token=first, context=builders.CONTEXT)
    assert tab_a.refresh.session_id == tab_b.refresh.session_id
    # ambas pestañas siguen con una sesión viva: el último token de la familia funciona
    refresh_orchestrator.refresh(
        uow=uow, refresh_token=tab_b.refresh.refresh_token, context=builders.CONTEXT
    )
    with db.connect() as conn:
        session_row = conn.execute(sa.select(sessions_orm.SessionOrm)).one()
        tokens = conn.execute(sa.select(sessions_orm.RefreshTokenOrm)).all()
    assert session_row.revoked_at is None and len(tokens) == 4
    assert sum(1 for t in tokens if t.rotated_at is None) == 1


def _after_grace() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(seconds=11)


def test_reset_password_revokes_every_session(db: sa.Engine) -> None:
    uow, mailer = unit_of_work.build(), capturing.CapturingMailer()
    _register_and_verify(uow, mailer)
    sessions_before = [_login(uow).tokens.refresh.refresh_token for _ in range(2)]
    users.request_password_reset(
        uow=uow,
        input_dto=users_dto.EmailInputDTO(email=_EMAIL),
        config=builders.CONFIG,
        context=builders.CONTEXT,
    )
    worker.run_once(uow, worker.build_handlers(mailer))
    token = helpers.token_from_message(mailer.to(_EMAIL)[-1])

    reset_password_orchestrator.reset_password(
        uow=uow,
        input_dto=users_dto.ResetPasswordInputDTO(token=token, password="nueva-contrasena-1"),
        config=builders.CONFIG,
    )

    for refresh_token in sessions_before:
        with pytest.raises(sessions_exceptions.RefreshTokenInvalidError):
            refresh_orchestrator.refresh(
                uow=uow, refresh_token=refresh_token, context=builders.CONTEXT
            )
    with db.connect() as conn:
        reasons = conn.execute(sa.select(sessions_orm.SessionOrm.revoke_reason)).scalars().all()
        version = conn.execute(sa.select(users_orm.UserOrm.credentials_version)).scalar_one()
    assert reasons == ["password_reset", "password_reset"] and version == 2


def test_rate_limit_counter_survives_failed_logins(db: sa.Engine) -> None:
    """Postgres: el intento cuenta aunque el caso de uso haga rollback."""
    uow = unit_of_work.build()
    login = users_dto.LoginInputDTO(email="nadie@example.com", password="lo-que-sea-1")
    with time_machine.travel(_MINUTE_START, tick=False) as clock:
        for _ in range(5):
            with pytest.raises(commons_exceptions.UnauthorizedError):
                users.authenticate(uow=uow, input_dto=login, context=builders.CONTEXT)
            clock.shift(datetime.timedelta(seconds=9))  # deja pasar el retardo creciente
        with pytest.raises(commons_exceptions.TooManyRequestsError) as info:
            users.authenticate(uow=uow, input_dto=login, context=builders.CONTEXT)
    assert info.value.retry_after_seconds == 15
    with db.connect() as conn:
        hits = dict(
            conn.execute(sa.select(orm_base.RateLimitOrm.bucket, orm_base.RateLimitOrm.hits))
            .tuples()
            .all()
        )
    # La global por correo (que no depende de la IP) no cuenta el 6.º: el 429 llegó antes.
    assert hits == {"login:10.0.0.1|nadie@example.com": 6, "login_email:nadie@example.com": 5}


_MINUTE_START = datetime.datetime(2030, 1, 7, 10, 0, 0, tzinfo=datetime.UTC)


def test_login_backoff_is_persisted_and_counted_in_postgres(db: sa.Engine) -> None:
    uow, mailer = unit_of_work.build(), capturing.CapturingMailer()
    _register_and_verify(uow, mailer)
    wrong = users_dto.LoginInputDTO(email=_EMAIL, password="no-es-la-clave")
    with time_machine.travel(_MINUTE_START, tick=False) as clock:
        for _ in range(3):
            with pytest.raises(commons_exceptions.UnauthorizedError):
                users.authenticate(uow=uow, input_dto=wrong, context=builders.CONTEXT)
        with pytest.raises(commons_exceptions.TooManyRequestsError) as info:
            _login(uow)
        assert info.value.retry_after_seconds == 2
        with db.connect() as conn:
            row = conn.execute(sa.select(orm_base.BackoffCounterOrm)).one()
        assert row.failures == 3 and row.bucket.startswith("login_backoff:")
        clock.shift(datetime.timedelta(seconds=2))
        _login(uow)
    with db.connect() as conn:
        assert conn.execute(sa.select(orm_base.BackoffCounterOrm)).all() == []


def test_duplicate_registration_race_is_absorbed(db: sa.Engine) -> None:
    uow = unit_of_work.build()
    body = users_dto.RegisterInputDTO(
        email=_EMAIL, full_name="Linus", password=_PASSWORD, accept_data_policy=True
    )
    users.register(uow=uow, input_dto=body, config=builders.CONFIG, context=builders.CONTEXT)
    with db.begin() as conn:  # simula otro registro concurrente insertando por debajo
        conn.execute(sa.update(users_orm.UserOrm).values(email="otro@example.com"))
    users.register(uow=uow, input_dto=body, config=builders.CONFIG, context=builders.CONTEXT)
    with db.connect() as conn:
        assert (
            conn.execute(sa.select(sa.func.count()).select_from(users_orm.UserOrm)).scalar_one()
            == 2
        )
