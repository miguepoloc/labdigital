"""Generic Repository port — ARCHITECTURE.md §7. A repository is a port like any other:
the domain declares what it needs, an adapter provides it. Bespoke query methods (e.g.
get_by_sku) go directly on the concrete repository class, never on this generic interface.

`add`/`update`, not one unified `put` — verified against `sona-sso-backend`'s real
`OrganizationRepository`: insert and update are different operations with different
failure modes (a HumanFriendlyId-keyed `add` can collide on the primary key and must
retry with a fresh id, §5.2; `update` can lose an optimistic-concurrency race, §8.1) —
collapsing them into one `session.merge(...)`-based `put` hides which one a caller means
and can't express the collision-retry path at all."""

import abc
from typing import Any

from backend.commons.domain import aggregates


class Repository[T: aggregates.AggregateRoot](abc.ABC):
    @abc.abstractmethod
    def get(self, id: Any) -> T: ...  # noqa: A002 - matches the domain vocabulary

    @abc.abstractmethod
    def add(self, entity: T) -> None:
        """Inserts a brand-new aggregate instance. Drains and records its events (§11.2) —
        never call `entity.pull_events()` again after this returns."""

    @abc.abstractmethod
    def update(self, entity: T) -> None:
        """Persists a mutation to an aggregate that already exists. Raises
        `ConcurrentModificationError` on a lost optimistic-concurrency race (§8.1). Drains
        and records its events (§11.2) — never call `entity.pull_events()` again after this
        returns."""

    @abc.abstractmethod
    def delete(self, id: Any) -> None: ...  # noqa: A002
