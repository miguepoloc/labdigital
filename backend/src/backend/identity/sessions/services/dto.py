from typing import Self

from backend.commons.application import dto
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.sessions.domain.model import aggregate


def _iso(value: base_value_objects.PosixTime) -> str:
    return value.to_datetime().isoformat().replace("+00:00", "Z")


class StartSessionInputDTO(dto.BaseDTO):
    user_id: str
    credentials_version: int
    persistent: bool
    ip: str
    user_agent: str = ""


class IssuedRefreshOutputDTO(dto.BaseDTO):
    """El refresh en claro sólo vive aquí, de camino a la cookie."""

    session_id: str
    user_id: str
    credentials_version: int
    refresh_token: str
    persistent: bool
    refresh_expires_at_microseconds: int


class SessionOutputDTO(dto.BaseDTO):
    """`Session` del contrato §4 (`GET /auth/sessions`)."""

    id: str
    user_agent: str
    ip: str
    created_at: str
    last_used_at: str
    expires_at: str
    persistent: bool
    current: bool

    @classmethod
    def from_entity(cls, session: aggregate.Session, *, current_session_id: str | None) -> Self:
        return cls(
            id=str(session.id),
            user_agent=session.user_agent,
            ip=session.ip,
            created_at=_iso(session.created_at),
            last_used_at=_iso(session.last_used_at),
            expires_at=_iso(session.refresh_expires_at()),
            persistent=session.persistent,
            current=str(session.id) == current_session_id,
        )
