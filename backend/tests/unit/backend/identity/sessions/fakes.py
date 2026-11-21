"""Fake en memoria de `DefaultSessionRepository`, con historial de tokens (para reuso)."""

from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.sessions.domain.model import aggregate, exceptions, value_objects
from tests.unit import fakes


class FakeSessionRepository(repositories.Repository[aggregate.Session]):
    def __init__(self, outbox: fakes.FakeOutbox) -> None:
        self._outbox = outbox
        self.by_id: dict[value_objects.SessionId, aggregate.Session] = {}
        self.tokens: dict[
            value_objects.RefreshTokenId,
            tuple[value_objects.SessionId, value_objects.RefreshTokenRecord],
        ] = {}

    def get(self, id: value_objects.SessionId) -> aggregate.Session:  # noqa: A002
        try:
            return self.by_id[id].model_copy(deep=True)
        except KeyError:
            raise exceptions.SessionNotFoundError() from None

    def find_by_token_id(
        self, token_id: value_objects.RefreshTokenId
    ) -> tuple[aggregate.Session, value_objects.RefreshTokenRecord] | None:
        found = self.tokens.get(token_id)
        if found is None:
            return None
        session_id, record = found
        return self.get(session_id), record

    def list_active_for_user(
        self, user_id: identity_value_objects.UserId
    ) -> list[aggregate.Session]:
        return [
            s.model_copy(deep=True)
            for s in self.by_id.values()
            if s.user_id == user_id and s.is_active()
        ]

    def delete_expired(self, *, older_than: base_value_objects.PosixTime) -> int:
        return 0

    def add(self, session: aggregate.Session) -> None:
        self.update(session)

    def update(self, session: aggregate.Session) -> None:
        now = base_value_objects.PosixTime.now()
        for token_id, (session_id, record) in list(self.tokens.items()):
            if (
                session_id == session.id
                and token_id != session.current_token.id
                and record.rotated_at is None
            ):
                self.tokens[token_id] = (session_id, record.model_copy(update={"rotated_at": now}))
        self.tokens.setdefault(session.current_token.id, (session.id, session.current_token))
        fakes.drain_events(session, self._outbox)
        self.by_id[session.id] = session.model_copy(deep=True)

    def delete(self, id: value_objects.SessionId) -> None:  # noqa: A002
        self.by_id.pop(id, None)
