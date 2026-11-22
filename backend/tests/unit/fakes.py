"""Piezas compartidas para tests unitarios — ARCHITECTURE.md §15 ("fakes, no mocks").

`FakeUnitOfWork` imita la superficie pública de `unit_of_work.UnitOfWork` que usan los
servicios (`transaction()`, `repo()`, `audit`, `outbox`, `rate_limits`) sin Postgres. Las
transacciones del fake no hacen rollback: los tests sólo afirman sobre lo que un servicio
deja confirmado, y los casos de rollback real se cubren en integración."""

from collections.abc import Generator
import contextlib
from typing import Any

from backend.commons.domain import (
    aggregates,
    audit,
    events,
    rate_limits,
    repositories,
    value_objects,
)


class FakeOutbox:
    def __init__(self) -> None:
        self.recorded: list[events.DomainEvent] = []

    def record(self, event: events.DomainEvent) -> None:
        self.recorded.append(event)

    def of_type(self, event_type: type[events.DomainEvent]) -> list[Any]:
        return [e for e in self.recorded if isinstance(e, event_type)]


def drain_events(entity: aggregates.AggregateRoot[Any], outbox: FakeOutbox) -> None:
    for event in entity.pull_events():
        outbox.record(event)


class FakeAuditRepository:
    def __init__(self) -> None:
        self.entries: list[audit.AuditEntry] = []

    def add(self, entry: audit.AuditEntry) -> None:
        self.entries.append(entry)

    def actions(self) -> list[str]:
        return [e.action for e in self.entries]


class FakeRateLimits:
    """Ventana fija como `RateLimitRepository` (respeta `time_machine`)."""

    def __init__(self) -> None:
        self.hits: dict[str, int] = {}

    def hit(self, rule: rate_limits.RateLimitRule, key: str) -> int | None:
        now = value_objects.PosixTime.now().microseconds // 1_000_000
        window_start = now - now % rule.window_seconds
        bucket = f"{rule.name}:{key}:{window_start}"
        self.hits[bucket] = self.hits.get(bucket, 0) + 1
        if self.hits[bucket] > rule.limit:
            return max(1, window_start + rule.window_seconds - now)
        return None


class FakeBackoff:
    """Misma semántica que `BackoffRepository`, en memoria (respeta `time_machine`)."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[int, int, int]] = {}  # failures, last_failure, blocked_until

    @staticmethod
    def _now() -> int:
        return value_objects.PosixTime.now().microseconds // 1_000_000

    def retry_after(self, rule: rate_limits.BackoffRule, key: str) -> int | None:
        row = self.rows.get(f"{rule.name}:{key}")
        now = self._now()
        if row is None or row[2] <= now:
            return None
        return row[2] - now

    def record_failure(self, rule: rate_limits.BackoffRule, key: str) -> int:
        bucket, now = f"{rule.name}:{key}", self._now()
        failures, last, _ = self.rows.get(bucket, (0, now, 0))
        failures = 1 if now - last > rule.reset_after_seconds else failures + 1
        delay = rule.delay_after(failures)
        self.rows[bucket] = (failures, now, now + delay)
        return delay

    def reset(self, rule: rate_limits.BackoffRule, key: str) -> None:
        self.rows.pop(f"{rule.name}:{key}", None)


class FakeUnitOfWork:
    def __init__(self, repos: dict[type[aggregates.AggregateRoot[Any]], Any] | None = None) -> None:
        self._repos: dict[type[aggregates.AggregateRoot[Any]], Any] = repos or {}
        self.outbox = FakeOutbox()
        self.audit = FakeAuditRepository()
        self.rate_limits = FakeRateLimits()
        self.backoff = FakeBackoff()
        self.transactions = 0

    def register(self, aggregate_type: type[aggregates.AggregateRoot[Any]], repo: Any) -> None:
        self._repos[aggregate_type] = repo

    def repo[T: aggregates.AggregateRoot[Any]](
        self, aggregate_type: type[T]
    ) -> repositories.Repository[T]:
        return self._repos[aggregate_type]

    @contextlib.contextmanager
    def transaction(self, *, idempotency_key: str | None = None) -> Generator[None]:
        del idempotency_key
        self.transactions += 1
        yield
