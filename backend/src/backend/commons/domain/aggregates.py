"""Base AggregateRoot — ARCHITECTURE.md §5.1/§8.1.

Generic over its ID type (PEP 695) so mypy/pyright catch cross-aggregate ID confusion at
build time — see ARCHITECTURE.md §5.1 for why this is generic when bold's equivalent isn't
(bold type-checks with mypy against Pydantic v1, which doesn't flag narrowing a mutable
field's type in a subclass; this codebase uses pyright + Pydantic v2, which does).
"""

import pydantic

from backend.commons.domain import entities, value_objects
from backend.commons.domain import events as domain_events


class AggregateRoot[IdT](entities.Entity[IdT]):
    version: int = 0  # optimistic concurrency — ARCHITECTURE.md §8.1
    _events: list[domain_events.DomainEvent] = pydantic.PrivateAttr(default_factory=list)

    def touch(self) -> None:
        """Bumps `updated_at` — call at the end of every command method that changes state
        (ARCHITECTURE.md §5.1a). Replaces `self.updated_at = value_objects.PosixTime.now()`
        repeated inline in every command, the way bold's own aggregates do it (verified
        against `bancolombia_cardless_cashout/domain/model/aggregate.py`'s `_change_status`,
        which sets `last_update_date` in one place rather than at every call site)."""
        self.updated_at = value_objects.PosixTime.now()

    def record_event(self, event: domain_events.DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[domain_events.DomainEvent]:
        """Rule, non-negotiable (§1.6): a subcontext's services/<subcontext>.py must call
        this and write the result to the outbox inside the same transaction as the
        mutation. sona-sso-backend shipped the alternative — silently — to production."""
        pulled, self._events = self._events, []
        return pulled
