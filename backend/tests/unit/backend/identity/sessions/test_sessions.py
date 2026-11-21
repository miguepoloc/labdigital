import datetime

import pytest
import time_machine

from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.sessions.domain.model import aggregate, exceptions, value_objects
from backend.identity.sessions.services import dto, sessions
from tests.unit.backend.identity import builders

pytestmark = pytest.mark.unit

_USER = identity_value_objects.UserId.new()


def _after_grace() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(seconds=11)


def _start(persistent: bool = True) -> tuple[aggregate.Session, value_objects.OpaqueRefreshToken]:
    return aggregate.Session.start(
        user_id=_USER, credentials_version=1, persistent=persistent, user_agent="ua", ip="1.1.1.1"
    )


def test_redeem_rotates_current_token() -> None:
    session, opaque = _start()
    old = session.current_token
    result = session.redeem(presented=old, secret=opaque.secret, ip="2.2.2.2", user_agent="ua2")
    assert result.outcome is value_objects.RedeemOutcome.ROTATED
    assert result.new_token is not None and result.new_token.token_id != old.id
    assert session.current_token.id == result.new_token.token_id
    assert session.ip == "2.2.2.2"


def test_redeem_old_token_is_reuse_and_revokes_family() -> None:
    session, opaque = _start()
    old = session.current_token
    session.redeem(presented=old, secret=opaque.secret, ip="x", user_agent="x")
    rotated_old = old.model_copy(update={"rotated_at": session.updated_at})

    with time_machine.travel(_after_grace()):
        result = session.redeem(presented=rotated_old, secret=opaque.secret, ip="x", user_agent="x")

    assert result.outcome is value_objects.RedeemOutcome.REUSED
    assert session.is_revoked and session.revoke_reason is value_objects.RevokeReason.REFRESH_REUSE


def test_wrong_secret_does_not_revoke() -> None:
    session, _ = _start()
    result = session.redeem(
        presented=session.current_token, secret="adivinado", ip="x", user_agent="x"
    )
    assert result.outcome is value_objects.RedeemOutcome.INVALID
    assert not session.is_revoked


def test_ephemeral_session_expires_after_a_day_idle() -> None:
    session, opaque = _start(persistent=False)
    later = datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(hours=25)
    with time_machine.travel(later):
        result = session.redeem(
            presented=session.current_token, secret=opaque.secret, ip="x", user_agent="x"
        )
    assert result.outcome is value_objects.RedeemOutcome.INVALID


def _service_start(f: builders.IdentityFakes) -> dto.IssuedRefreshOutputDTO:
    return sessions.start_session(
        uow=f.uow,  # type: ignore[arg-type]
        input_dto=dto.StartSessionInputDTO(
            user_id=str(_USER), credentials_version=1, persistent=True, ip="1.1.1.1"
        ),
    )


def test_service_rotation_and_reuse_detection_with_audit() -> None:
    f = builders.build()
    first = _service_start(f)
    second = sessions.rotate(uow=f.uow, refresh_token=first.refresh_token, ip="i", user_agent="u")  # type: ignore[arg-type]
    assert second.refresh_token != first.refresh_token and second.session_id == first.session_id

    with time_machine.travel(_after_grace()), pytest.raises(exceptions.RefreshTokenInvalidError):
        sessions.rotate(uow=f.uow, refresh_token=first.refresh_token, ip="i", user_agent="u")  # type: ignore[arg-type]
    assert "refresh_reuse_detected" in f.uow.audit.actions()
    # la familia entera cayó: el token "bueno" tampoco sirve
    with pytest.raises(exceptions.RefreshTokenInvalidError):
        sessions.rotate(uow=f.uow, refresh_token=second.refresh_token, ip="i", user_agent="u")  # type: ignore[arg-type]


@pytest.mark.parametrize("garbage", ["", "sin-punto", "no-uuid.secreto"])
def test_malformed_refresh_is_invalid(garbage: str) -> None:
    f = builders.build()
    with pytest.raises(exceptions.RefreshTokenInvalidError):
        sessions.rotate(uow=f.uow, refresh_token=garbage, ip="i", user_agent="u")  # type: ignore[arg-type]


def test_revoke_others_keeps_current_and_ownership_is_enforced() -> None:
    f = builders.build()
    a, b, c = _service_start(f), _service_start(f), _service_start(f)
    revoked = sessions.revoke_all_for_user(
        uow=f.uow,  # type: ignore[arg-type]
        user_id=str(_USER),
        reason=value_objects.RevokeReason.REVOKED_OTHERS,
        keep_session_id=a.session_id,
    )
    assert revoked == 2
    listed = sessions.list_active(uow=f.uow, user_id=str(_USER), current_session_id=a.session_id)  # type: ignore[arg-type]
    assert [s.id for s in listed] == [a.session_id] and listed[0].current
    assert {b.session_id, c.session_id}.isdisjoint({s.id for s in listed})
    with pytest.raises(exceptions.SessionNotFoundError):
        sessions.revoke_session(
            uow=f.uow,  # type: ignore[arg-type]
            session_id=a.session_id,
            owner_user_id=str(identity_value_objects.UserId.new()),
            reason=value_objects.RevokeReason.REVOKED_BY_USER,
        )


def test_redeem_just_rotated_token_within_grace_rotates_same_family() -> None:
    session, opaque = _start()
    old = session.current_token
    first = session.redeem(presented=old, secret=opaque.secret, ip="x", user_agent="x")
    rotated_old = old.model_copy(update={"rotated_at": session.updated_at})
    with time_machine.travel(
        datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(seconds=9)
    ):
        again = session.redeem(presented=rotated_old, secret=opaque.secret, ip="x", user_agent="x")
    assert again.outcome is value_objects.RedeemOutcome.ROTATED_IN_GRACE
    assert again.new_token is not None and first.new_token is not None
    assert again.new_token.token_id not in (first.new_token.token_id, old.id)
    assert session.current_token.id == again.new_token.token_id and not session.is_revoked


def test_service_concurrent_refresh_within_grace_keeps_family_alive() -> None:
    f = builders.build()
    first = _service_start(f)
    tab_a = sessions.rotate(uow=f.uow, refresh_token=first.refresh_token, ip="i", user_agent="u")  # type: ignore[arg-type]
    tab_b = sessions.rotate(uow=f.uow, refresh_token=first.refresh_token, ip="i", user_agent="u")  # type: ignore[arg-type]
    assert tab_b.session_id == tab_a.session_id == first.session_id
    assert tab_b.refresh_token not in (tab_a.refresh_token, first.refresh_token)
    assert "refresh_reuse_detected" not in f.uow.audit.actions()
    # la familia sigue viva: el último token funciona
    later = sessions.rotate(uow=f.uow, refresh_token=tab_b.refresh_token, ip="i", user_agent="u")  # type: ignore[arg-type]
    assert later.session_id == first.session_id
