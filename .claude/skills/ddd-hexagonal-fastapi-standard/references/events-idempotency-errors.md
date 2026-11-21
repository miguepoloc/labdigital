# Domain events, the outbox, idempotency, and errors

> Topic excerpt of `../../../ARCHITECTURE.md` §11–§13. If this file and `ARCHITECTURE.md`
> disagree, `ARCHITECTURE.md` wins.

## §11. Domain events and the Outbox pattern

### §11.1 Event hierarchy

```python
# commons/domain/events.py
import uuid

import pydantic

from commons.domain import value_objects


class DomainEvent(value_objects.ValueObject):
    event_id: uuid.UUID
    occurred_at: value_objects.PosixTime

    @pydantic.computed_field
    @property
    def event_type(self) -> str:
        """Serialized alongside every event; the ONE source of truth for its wire name.

        Never hand-maintain a parallel string constant for this — that duplication is
        exactly what let `sona`'s own event map drift from its event classes in practice
        (its own troubleshooting notes list "unmapped event names" as a recurring failure).
        A computed field can't drift from the class name, because it *is* the class name.
        """
        return type(self).__name__

    def idempotence_key(self) -> str:
        """Override when a business key is more meaningful than event_id (e.g.
        f"{type(self).__name__}-{self.aggregate_id}") — ported from bold's Event base."""
        return f"{type(self).__name__}-{self.event_id}"


class IntegrationEvent(DomainEvent):
    """A DomainEvent promoted to cross a bounded-context boundary — its own class, a public
    contract, not the internal domain event reused verbatim. Only IntegrationEvent
    subclasses are ever relayed out of the outbox (§11.2)."""
```

### §11.2 Why Outbox is mandatory, not optional

- `sona` (DynamoDB) gets atomicity **for free** — `uow.publish()` writes the event inside
  the same `transact_write_items` call as the aggregate write.
- `sona-sso-backend` (Postgres) records events and **never publishes them** — the drain
  point was never built.
- Neither publishes-after-commit with a documented fallback for "commit succeeded, publish
  crashed" — that failure mode silently loses events wherever present.

Postgres doesn't give a cross-table transactional write against an external queue, so the
**Transactional Outbox** is the mechanism:

```python
# commons/adapters/orm_base.py  (continued)
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class OutboxEventOrm(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(sa.Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    idempotence_key: Mapped[str] = mapped_column(sa.Text, unique=True)
    created_at: Mapped[int] = mapped_column(sa.BigInteger)   # PosixTime microseconds
    published_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
```

- `uow.outbox.record(event)` (`domain-and-application.md` §6, `persistence-and-concurrency.md`
  §8) inserts a row **inside the same `with uow.transaction():`** as the aggregate write —
  the Postgres-native equivalent of what DynamoDB gives `bold` automatically.
- A separate **relay** (`cron`-triggered, polling every 10–30s — `bold`'s `EventsClient`
  interval) reads unpublished rows, publishes each to SNS/EventBridge, sets `published_at`.
  Only `IntegrationEvent` rows leave the process.
- Fan-out follows `sona`'s proven shape: SNS topic per product, filtered SQS queue per
  consumer, one Lambda per queue, DLQ + `maxReceiveCount` on every queue.

### §11.3 What NOT to build

No in-process message bus, no `Command` dataclasses, no `messagebus.handle()` dispatch
table. The outbox relay and event-consumer Lambda entrypoints
(`entrypoints-and-orchestration.md` §9.4) are the only "bus" here.

---

## §12. Idempotency

Two mechanisms, one underlying trick: claim a key inside the same transaction as the
effect, let a unique constraint deduplicate.

### §12.1 HTTP mutations — `Idempotency-Key` header

```python
# commons/adapters/orm_base.py  (continued)
class IdempotencyKeyOrm(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    created_at: Mapped[int] = mapped_column(sa.BigInteger)   # PosixTime microseconds
```

```python
@app.post("/orders")
def create_order(
    body: dto.CreateOrderInputDTO,
    idempotency_key: Annotated[str | None, fastapi.Header(alias="Idempotency-Key")] = None,
    ...
) -> dto.OrderOutputDTO:
    with uow.transaction(idempotency_key=idempotency_key):
        ...
```

A `UniqueViolation` raises `exceptions.DuplicatedTransactionError`, mapped to HTTP 409
`DUPLICATED_TRANSACTION` (§13 below). Scope to **creation** endpoints only —
`suspend`/`resume`/`delete` are already naturally idempotent at the domain level.

### §12.2 Event consumers — event-derived idempotency key

No second table — `IdempotencyKeyOrm` (§12.1) is reused as-is. `UnitOfWork.transaction
(idempotency_key=...)` is one generic mechanism with two call sites, not two mechanisms.

Same mechanism as §12.1, fed `event.idempotence_key()` (§11.1 above) instead of a client
header — this is exactly what `bold` does with its own `idempotence_key`, just on Postgres's
native primitive instead of a separate system. A duplicate SQS delivery hits the unique
constraint, the transaction rolls back cleanly, the handler catches
`DuplicatedTransactionError` and returns — acknowledged, not retried, not double-applied.

---

## §13. Error handling and exception hierarchy

```python
# commons/domain/exceptions.py
class DomainError(Exception):
    def __init__(self, message: str, *, code: str, retriable: bool = False,
                 details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retriable = retriable
        self.details = details or {}


class NotFoundError(DomainError): pass
class ConflictError(DomainError): pass
class ValidationError(DomainError): pass
class UnauthorizedError(DomainError): pass
class ForbiddenError(DomainError): pass
class DuplicatedTransactionError(ConflictError): pass
class ConcurrentModificationError(ConflictError): pass   # a write lost a race — see
                                                           # persistence-and-concurrency.md §8.1
```

Every one of these is `pass`, not `...` — each is a complete, immediately instantiable class
(`raise NotFoundError("...")` works today, nothing left to fill in). See
`enforcement-and-style.md` for the full `...` vs. `pass` rule.

Ported from `sona-sso-backend` over `bold`'s `CustomException(status_code, code,
exception_type)`, because the `retriable` flag is directly useful for event-consumer retry
logic in a way a raw HTTP status code isn't. Every subcontext's `exceptions.py` subclasses
one of these:

```python
# commons/adapters/api/exception_handler.py
from commons.domain import exceptions

_STATUS_FOR: dict[type[exceptions.DomainError], int] = {
    exceptions.NotFoundError: 404, exceptions.ConflictError: 409,
    exceptions.ValidationError: 422, exceptions.UnauthorizedError: 401,
    exceptions.ForbiddenError: 403,
}


def status_for(error: exceptions.DomainError) -> int:
    for error_type, status in _STATUS_FOR.items():
        if isinstance(error, error_type):
            return status
    return 500
```

This is the **only** place HTTP status codes get decided. `ConcurrentModificationError` and
`DuplicatedTransactionError` need no entry of their own — they're `ConflictError` subclasses,
and the `isinstance` check already resolves them to 409.
