"""Fakes en memoria de los repositorios de `identity.users`."""

from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.users.domain.model import aggregate, exceptions, value_objects
from tests.unit import fakes


class FakeUserRepository(repositories.Repository[aggregate.User]):
    def __init__(self, outbox: fakes.FakeOutbox) -> None:
        self._outbox = outbox
        self.by_id: dict[identity_value_objects.UserId, aggregate.User] = {}

    def get(self, id: identity_value_objects.UserId) -> aggregate.User:  # noqa: A002
        try:
            return self.by_id[id].model_copy(deep=True)
        except KeyError:
            raise exceptions.UserNotFoundError(identifier=id) from None

    def get_by_email(self, email: value_objects.Email) -> aggregate.User:
        for user in self.by_id.values():
            if user.email == email:
                return user.model_copy(deep=True)
        raise exceptions.UserNotFoundError(identifier=email)

    def add(self, user: aggregate.User) -> None:
        if any(u.email == user.email for u in self.by_id.values()):
            raise exceptions.UserAlreadyExistsError()
        fakes.drain_events(user, self._outbox)
        self.by_id[user.id] = user.model_copy(deep=True)

    def update(self, user: aggregate.User) -> None:
        fakes.drain_events(user, self._outbox)
        self.by_id[user.id] = user.model_copy(deep=True)

    def delete(self, id: identity_value_objects.UserId) -> None:  # noqa: A002
        self.by_id.pop(id, None)


class FakeEmailTokenRepository(repositories.Repository[aggregate.EmailToken]):
    def __init__(self, outbox: fakes.FakeOutbox) -> None:
        self._outbox = outbox
        self.by_id: dict[value_objects.EmailTokenId, aggregate.EmailToken] = {}

    def get(self, id: value_objects.EmailTokenId) -> aggregate.EmailToken:  # noqa: A002
        try:
            return self.by_id[id].model_copy(deep=True)
        except KeyError:
            raise exceptions.InvalidEmailTokenError() from None

    def get_by_secret(
        self, secret: str, *, purpose: value_objects.EmailTokenPurpose
    ) -> aggregate.EmailToken:
        token_hash = value_objects.hash_token_secret(secret)
        for token in self.by_id.values():
            if token.token_hash == token_hash and token.purpose is purpose:
                return token.model_copy(deep=True)
        raise exceptions.InvalidEmailTokenError()

    def invalidate_open(
        self, *, user_id: identity_value_objects.UserId, purpose: value_objects.EmailTokenPurpose
    ) -> None:
        now = base_value_objects.PosixTime.now()
        for token_id, token in list(self.by_id.items()):
            if token.user_id == user_id and token.purpose is purpose and token.used_at is None:
                self.by_id[token_id] = token.model_copy(update={"used_at": now})

    def delete_expired(self, *, older_than: base_value_objects.PosixTime) -> int:
        stale = [k for k, t in self.by_id.items() if t.expires_at < older_than]
        for key in stale:
            del self.by_id[key]
        return len(stale)

    def add(self, token: aggregate.EmailToken) -> None:
        fakes.drain_events(token, self._outbox)
        self.by_id[token.id] = token.model_copy(deep=True)

    def update(self, token: aggregate.EmailToken) -> None:
        self.add(token)

    def delete(self, id: value_objects.EmailTokenId) -> None:  # noqa: A002
        self.by_id.pop(id, None)
