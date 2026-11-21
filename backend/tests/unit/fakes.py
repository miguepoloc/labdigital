"""Shared building blocks for domain/service unit tests — ARCHITECTURE.md §15,
`shared-kernel-and-testing.md`. `FakeUnitOfWork` implements the subset of the real
`unit_of_work.UnitOfWork`'s public surface `services/*.py` and the orchestrators actually
call (`.transaction()`, `.repo(...)`, `.audit`, `.outbox`) without ever opening a real
SQLAlchemy `Session` — what makes those functions testable in milliseconds, no Postgres
required (ARCHITECTURE.md §15's "Fakes, not mocks" row).

Not checked by `mypy src` — the Makefile's `typecheck` target (and this repo's CI) only
type-checks `src/`, matching `pyproject.toml`'s `testpaths = ["tests"]` staying separate
from `[tool.hatch.build.targets.wheel] packages = ["src/backend"]`. `FakeUnitOfWork` is
therefore a plain duck-typed stand-in, not a subclass of `UnitOfWork` (that class's
`__init__` requires a `sessionmaker[Session]` and its own `.session` property is meant to
raise outside a transaction — inheriting it would mean overriding away everything
session-shaped rather than reusing anything, the same "don't override away unwanted
behavior" reasoning `commons.domain.entities.Entity` is kept minimal for,
`anti-patterns-and-design-principles.md` §22.1's Refused Bequest entry)."""

from collections.abc import Generator
import contextlib
from typing import Any

from backend.commons.domain import aggregates, audit, events, repositories


class FakeOutbox:
    """Stands in for the real `OutboxRepository` (commons/adapters/outbox.py) — a
    `Fake<Aggregate>Repository.add`/`.update` drains `entity.pull_events()` into this
    directly, the same tail every real repository's `add`/`update` runs through
    `repository_helpers.publish_events`, just with no session behind it."""

    def __init__(self) -> None:
        self.recorded: list[events.DomainEvent] = []

    def record(self, event: events.DomainEvent) -> None:
        self.recorded.append(event)


def drain_events(entity: aggregates.AggregateRoot[Any], outbox: FakeOutbox) -> None:
    """Call from every `Fake<Aggregate>Repository.add`/`.update` — mirrors
    `repository_helpers.publish_events`, so a unit test can assert on `outbox.recorded`
    exactly the way an integration test asserts on the real `outbox_events` table rows."""
    for event in entity.pull_events():
        outbox.record(event)


class FakeAuditRepository:
    """Stands in for `commons.adapters.audit.AuditRepository` — same `.add` signature, no
    session, no `list_for_aggregate` (nothing under test reads it back yet)."""

    def __init__(self) -> None:
        self.entries: list[audit.AuditEntry] = []

    def add(self, entry: audit.AuditEntry) -> None:
        self.entries.append(entry)


class FakeUnitOfWork:
    """Constructed with the fake repositories a test needs, keyed by aggregate type — the
    same registry shape `unit_of_work.register_repo` builds for the real one at import time,
    just supplied directly instead. One `FakeOutbox`/`FakeAuditRepository` per instance
    (not re-created per `.audit`/`.outbox` access like the real property does per-session) —
    stable objects a test can assert against after the fact."""

    def __init__(self, repos: dict[type[aggregates.AggregateRoot[Any]], Any]) -> None:
        self._repos = repos
        self.outbox = FakeOutbox()
        self.audit = FakeAuditRepository()

    def repo[T: aggregates.AggregateRoot[Any]](
        self, aggregate_type: type[T]
    ) -> repositories.Repository[T]:
        return self._repos[aggregate_type]

    @contextlib.contextmanager
    def transaction(self, *, idempotency_key: str | None = None) -> Generator[None]:
        del idempotency_key  # no idempotency table to collide against in-memory — real
        # idempotency-key rejection is integration-test territory (ARCHITECTURE.md
        # §12.1/§12.2's unique-constraint mechanism), not what this fake exists to cover.
        yield
