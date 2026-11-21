"""In-memory fake for `identity.users.adapters.repository.DefaultUserRepository` —
`shared-kernel-and-testing.md`'s `FakeStockRepository` shape, applied to `User`. Extends the
generic `Repository[T]` contract with the bespoke `get_by_email` query, and drains `add`/
`update` into the shared `FakeOutbox` (ARCHITECTURE.md §7/§11.2/§15)."""

from backend.commons.domain import repositories
from backend.identity.users.domain.model import aggregate, exceptions, value_objects
from tests.unit import fakes


class FakeUserRepository(repositories.Repository[aggregate.User]):
    def __init__(self, outbox: fakes.FakeOutbox) -> None:
        self._outbox = outbox
        self._by_id: dict[value_objects.UserId, aggregate.User] = {}

    def get(self, id: value_objects.UserId) -> aggregate.User:  # noqa: A002
        try:
            return self._by_id[id]
        except KeyError:
            raise exceptions.UserNotFoundError(identifier=id) from None

    def get_by_email(self, email: value_objects.Email) -> aggregate.User:
        for user in self._by_id.values():
            if user.email == email:
                return user
        raise exceptions.UserNotFoundError(identifier=email)

    def add(self, user: aggregate.User) -> None:
        self._by_id[user.id] = user
        fakes.drain_events(user, self._outbox)

    def update(self, user: aggregate.User) -> None:
        self._by_id[user.id] = user
        fakes.drain_events(user, self._outbox)

    def delete(self, id: value_objects.UserId) -> None:  # noqa: A002
        self._by_id.pop(id, None)
