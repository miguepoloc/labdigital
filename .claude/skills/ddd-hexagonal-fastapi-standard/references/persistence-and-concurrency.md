# Adapters, Unit of Work, and optimistic concurrency

> Topic excerpt of `../../../ARCHITECTURE.md` §7–§8. If this file and `ARCHITECTURE.md`
> disagree, `ARCHITECTURE.md` wins.

## §7. Adapters — ORM mapping and repositories

Every concrete repository implements one shared contract, declared once in the domain layer
(a repository is a port like any other — the domain declares what it needs, an adapter
provides it):

```python
# commons/domain/repositories.py
import abc

from commons.domain import aggregates


class Repository[T: aggregates.AggregateRoot](abc.ABC):
    @abc.abstractmethod
    def get(self, id: object) -> T: ...

    @abc.abstractmethod
    def add(self, entity: T) -> None: ...

    @abc.abstractmethod
    def update(self, entity: T) -> None: ...

    @abc.abstractmethod
    def delete(self, id: object) -> None: ...
```

`...` marks these as method *stubs* with no body of their own — a contract, not an
implementation (see `enforcement-and-style.md` for the full `...` vs. `pass` rule).

**`add`/`update`, not one unified `put`** — verified against `sona-sso-backend`'s real
`OrganizationRepository` (`uow.organizations.add(org)` on creation,
`uow.organizations.update(org)` on every mutation, two distinct methods, never one). Insert
and update are different operations with different failure modes: an insert on a
`HumanFriendlyId`-keyed aggregate can collide on the primary key and must retry with a fresh
id (`domain-and-application.md` §5.2), an update can lose an §8.1 optimistic-concurrency
race. Collapsing both into one `session.merge(...)`-based `put` can't express the
collision-retry path at all and hides which operation a caller actually means.

PostgreSQL/SQLAlchemy requires an explicit relational mapping layer that `bold` (DynamoDB,
where the aggregate itself is what's serialized) doesn't need:

```python
# commons/adapters/orm_base.py
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampsMixin:
    """created_at/updated_at in POSIX microseconds (BigInteger) — never `datetime`."""
    created_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
```

```python
# commerce/stock/adapters/orm.py
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from commons.adapters import orm_base


class StockOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "stock"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(sa.Text, unique=True)
    available_quantity: Mapped[int]
```

```python
# commerce/stock/adapters/repository.py
from commons.domain import repositories, value_objects as base_value_objects

from commerce.commons import value_objects as commerce_value_objects
from commerce.stock.adapters import orm
from commerce.stock.domain.model import aggregate, exceptions, value_objects


def _to_orm(stock: aggregate.Stock) -> orm.StockOrm:
    return orm.StockOrm(
        id=stock.id.value, sku=stock.sku.value,
        available_quantity=stock.available_quantity,
        created_at=stock.created_at.microseconds, updated_at=stock.updated_at.microseconds,
    )


def _to_entity(stock_orm: orm.StockOrm) -> aggregate.Stock:
    return aggregate.Stock(
        id=value_objects.StockId(value=stock_orm.id),
        sku=commerce_value_objects.Sku(value=stock_orm.sku),
        available_quantity=stock_orm.available_quantity,
        created_at=base_value_objects.PosixTime(microseconds=stock_orm.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=stock_orm.updated_at),
    )


class DefaultStockRepository(repositories.Repository[aggregate.Stock]):
    def __init__(self, session: "orm.Session") -> None:
        self._session = session

    def add(self, stock: aggregate.Stock) -> None:
        # UuidV7Id-keyed — no insert_with_id_retry needed (§5.2), unlike Order below.
        self._session.add(_to_orm(stock))
        self._session.flush()
        repository_helpers.publish_events(self._session, stock)

    def update(self, stock: aggregate.Stock) -> None:
        self._session.merge(_to_orm(stock))
        try:
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                f"Stock [{stock.id}] changed concurrently — reload and retry.",
                code="CONCURRENT_MODIFICATION",
            ) from exc
        repository_helpers.publish_events(self._session, stock)

    def get_by_sku(self, sku: "commerce_value_objects.Sku") -> aggregate.Stock:
        stock_orm = self._session.execute(
            sa.select(orm.StockOrm).where(orm.StockOrm.sku == sku.value)
        ).scalar_one_or_none()
        if stock_orm is None:
            raise exceptions.StockNotFoundError(sku=sku)
        return _to_entity(stock_orm)
```

- `Mapped`/`mapped_column`/`DeclarativeBase` are imported **by name** — the one narrow,
  named exception to the module-import rule, matching Google's own carve-out for `typing`
  (see `enforcement-and-style.md`).
- Bespoke query methods (`get_by_sku`) go directly on the concrete repository class, not the
  generic `Repository[T]` interface — mirrors `bold`'s `custom_repo()` escape hatch below.
- `_to_orm`/`_to_entity` are plain module-level functions (`sona-sso-backend`'s convention).
- **Every `add`/`update` ends with `repository_helpers.publish_events(session, entity)`** —
  drains the entity's recorded events and records them to the outbox, in the *same*
  transaction as the write that just happened. This is why `services/*.py` never has a
  hand-called `_publish_events()` helper: a service can no longer forget to call it, since
  the repository does it unconditionally on every write. Verified against bold's own
  documented lifecycle: *"Repository persists atomically: `save(aggregate)` calls
  `uow.publish(event)` inside a transaction"* (`lambdas/CLAUDE.md`).
- **`stock.created_at.microseconds` here is not a Law-of-Demeter violation** — this pair of
  functions is the one place in the whole codebase authorized to unwrap a value object's
  internal field, because translating between the domain representation and the storage
  representation is their entire, sole purpose (the Data Mapper pattern, Fowler). The same
  access pattern anywhere in `domain/` or `services/` would be the mistake
  `anti-patterns-and-design-principles.md` calls out.

### §7.1 `add` on a `HumanFriendlyId`-keyed aggregate: `insert_with_id_retry`

`Order` (`domain-and-application.md` §5.2) is `HumanFriendlyId`-keyed, so its `add` can't
just `session.add(...)` and flush — a genuine, if rare, primary-key collision is possible:

```python
# commerce/orders/adapters/repository.py (excerpt)
from commons.adapters import repository_helpers

class DefaultOrderRepository(repositories.Repository[aggregate.Order]):
    ...
    def add(self, order: aggregate.Order) -> None:
        row = _to_orm(order)
        final_id = repository_helpers.insert_with_id_retry(self._session, row)
        if final_id != order.id.value:
            order.id = value_objects.OrderId(value=final_id)
        repository_helpers.publish_events(self._session, order)
```

```python
# commons/adapters/repository_helpers.py
def insert_with_id_retry[RowT: _HumanFriendlyIdRow](session: Session, row: RowT) -> str:
    table_name = row.__tablename__
    primary_key_constraint = f"{table_name}_pkey"   # Postgres's own default naming for an
    # inline PRIMARY KEY column constraint — this codebase sets no custom naming_convention
    # on Base.metadata, so this is what Postgres actually names it.
    for attempt in range(_MAX_ID_COLLISION_RETRIES):
        try:
            with session.begin_nested():            # a SAVEPOINT — see below
                session.add(row)
                session.flush()
            return str(row.id)
        except sqlalchemy.exc.IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
            if constraint != primary_key_constraint:
                raise   # a different unique-constraint conflict — not this helper's problem
            if attempt == _MAX_ID_COLLISION_RETRIES - 1:
                raise exceptions.ConflictError(..., code="ID_COLLISION", retriable=True) from exc
            row.id = value_objects.HumanFriendlyId.new().value   # try again with a fresh id
    raise AssertionError("unreachable")
```

**`session.begin_nested()` (a SAVEPOINT) is load-bearing, not decoration** — verified against
`sona-sso-backend`'s real `insert_with_id_retry`. Without it, catching the `IntegrityError`
and retrying would need a plain `session.rollback()` to clear the failed statement — but
`session.rollback()` rolls back the *entire* transaction, discarding every other write
already staged in the same `with uow.transaction():` block (a product-level orchestrator's
other mutations, `entrypoints-and-orchestration.md` §10.2), not just the colliding row.
`begin_nested()` scopes the rollback to just this attempt.

Only the primary-key constraint triggers a retry — any other `IntegrityError` (a genuine
unique-field violation) is re-raised immediately, since regenerating the id would silently
create a duplicate under a different key while leaving the real conflict unaddressed.

---

## §8. Unit of Work

**One generic `UnitOfWork` class for the whole codebase.** No per-context UoW subclasses —
`bold`'s `DefaultUnitOfWork` proves the generic-registry approach scales to dozens of
aggregate types without subclass proliferation, and avoids the unresolved tension
`sona-sso-backend`'s own `CLAUDE.md` flags in its per-Lambda UoW subclass matrix.

```python
# commons/adapters/unit_of_work.py
import contextlib
from typing import Iterator

from sqlalchemy.orm import Session, sessionmaker

from commons.domain import aggregates, repositories
from commons.adapters import orm_base, outbox   # orm_base: used by _claim_idempotency_key

_REPO_REGISTRY: dict[type[aggregates.AggregateRoot], type[repositories.Repository]] = {}


def register_repo(aggregate_type: type[aggregates.AggregateRoot],
                   repo_type: type[repositories.Repository]) -> None:
    _REPO_REGISTRY[aggregate_type] = repo_type


class UnitOfWork:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._repos: dict[type, repositories.Repository] = {}

    def repo[T: aggregates.AggregateRoot](self, aggregate_type: type[T]) -> repositories.Repository[T]:
        if aggregate_type not in self._repos:
            self._repos[aggregate_type] = _REPO_REGISTRY[aggregate_type](self._session)
        return self._repos[aggregate_type]

    @property
    def outbox(self) -> "outbox.OutboxRepository":
        return outbox.OutboxRepository(self._session)

    @contextlib.contextmanager
    def transaction(self, *, idempotency_key: str | None = None) -> Iterator[None]:
        if self._session is not None:
            yield   # nested call joins the outer transaction — no-op re-entrancy
            return
        self._session = self._session_factory()
        try:
            if idempotency_key is not None:
                self._claim_idempotency_key(idempotency_key)   # see events-idempotency-errors.md
            yield
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        finally:
            self._session.close()
            self._session = None
            self._repos.clear()
```

`_REPO_REGISTRY` is populated once at startup by each subcontext's `adapters/repository.py`
(`unit_of_work.register_repo(aggregate.Stock, repository.DefaultStockRepository)`),
analogous to `bold`'s `default_repo(root_entity_type)`.

**Nested transactions are how cross-service atomicity actually works** (see
`entrypoints-and-orchestration.md`'s orchestrator pattern): when a product-level orchestrator
opens `with uow.transaction():` and then calls a subcontext's service function, which itself
opens `with uow.transaction():`, the inner call detects `self._session is not None` and
joins the outer one — one commit, one rollback, for the whole call chain. This is the
mechanism, not an aside.

**Cross-aggregate atomicity policy:**

- **Within the same product**: atomic multi-aggregate transactions are allowed, achieved by
  nested `uow.transaction()` calls across service functions (never by an orchestrator
  calling `uow.repo()` directly).
- **Across products**: never share a transaction. Coordination goes through
  `orchestrators/` calling independently-committing service functions, or through the
  outbox — both in `entrypoints-and-orchestration.md` / `events-idempotency-errors.md`.

**No I/O inside an open transaction.** A `with uow.transaction():` block holds a checked-out
Postgres connection for its entire duration — a synchronous port call made while it's open
ties up that connection for the round-trip's full latency (and any `backoff` retry on it
multiplies that). Found as a real bug in this standard's own template: `confirm_order`
called `user_profile_port.get_profile(...)` from *inside* its transaction, contradicting the
rule its sibling `create_order` already followed. The fix has two parts, because a **nested**
`uow.transaction()` call joins the outer one as a no-op (above) — moving the port call inside
`orders.confirm_order`'s own transaction doesn't help once that function is called from
inside an orchestrator's already-open outer transaction. The port call has to move to
wherever the *outermost* transaction actually opens — see
`entrypoints-and-orchestration.md`'s worked `confirm_order_orchestrator.py` example, which
fetches the profile *before* opening its transaction and passes the plain
`shipping_name`/`shipping_email` strings down, not the port itself.

A plain read with no I/O (`orders.get_order`) staying wrapped in its own `with
uow.transaction():` is **not** a violation of this rule — verified against
`sona-sso-backend`'s own `OrganizationService.get()`, which wraps a pure read the same way.
SQLAlchemy always needs a `Session` for any query, read or write (unlike bold's DynamoDB
`find_by_id`, which needs no transactional envelope — that's an infrastructure difference,
not a reason to imitate the DynamoDB shape here). What matters is never letting a *held-open*
transaction span a network call.

## §8.1 Optimistic concurrency (race conditions)

The scenario this section exists for: two Lambda invocations both call
`stock_service.reserve_stock(sku=..., quantity=...)` for the same `Stock` at nearly the same
time. Both read `available_quantity=1`. Both decide there's enough. Without a check, both
write, and one write silently overwrites the other — stock gets sold twice.

`bold`'s real answer, verified against `commons/base_types.py` and
`commons/adapters/unit_of_work.py`: every `RootEntity` carries a `version:
RootEntityVersion` (a `number` that increments on every write); `_add_write_operation`
increments a *clone's* version and issues the DynamoDB conditional write expecting the
version it originally read — if another write already landed in between, the condition
fails and DynamoDB raises `ConcurrentModificationError`. `bold`'s own code comments the
correct response to it directly: *"forcing a new `find_by_id` or `query` call"* — the
caller re-fetches the current state and retries, it is not something to blindly retry with
the same stale in-memory aggregate.

PostgreSQL/SQLAlchemy has a native equivalent that needs none of DynamoDB's manual
bookkeeping — `version_id_col`, SQLAlchemy's built-in optimistic-locking column. Declaring
it makes every `UPDATE` include `WHERE version = :expected_version` and increments the
column automatically; zero rows affected raises `sqlalchemy.orm.exc.StaleDataError`. This is
the same pattern as `bold`'s, translated to the technology that already provides it, so
`AggregateRoot.version` (`domain-and-application.md` §5.1) stays a plain `int` — no need for
`bold`'s richer `RootEntityVersion` (`number`/`region`/`date`), which exists specifically to
make a conditional check DynamoDB doesn't provide natively; Postgres already provides it:

```python
# commerce/stock/adapters/orm.py  (excerpt — extends StockOrm above)
class StockOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "stock"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(sa.Text, unique=True)
    available_quantity: Mapped[int]
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}
```

`commons.domain.exceptions.ConcurrentModificationError` — a `ConflictError` subclass, see
`events-idempotency-errors.md` — is what the repository below raises on a lost race:

```python
# commerce/stock/adapters/repository.py  (excerpt — extends DefaultStockRepository above)
import sqlalchemy.orm.exc

from commons.domain import exceptions as commons_exceptions


class DefaultStockRepository(repositories.Repository[aggregate.Stock]):
    ...

    def update(self, stock: aggregate.Stock) -> None:
        self._session.merge(_to_orm(stock))
        try:
            self._session.flush()   # forces the version check now, not at commit time
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                f"Stock [{stock.id}] changed concurrently — reload and retry.",
                code="CONCURRENT_MODIFICATION",
            ) from exc
        repository_helpers.publish_events(self._session, stock)
```

`commons_exceptions` is an alias — this file already imports its own subcontext's
`exceptions` module for `StockNotFoundError`; without the alias the two would collide (see
`enforcement-and-style.md`). `ConcurrentModificationError` is a `ConflictError` subclass, so
it needs no new entry in the HTTP-status-mapping table
(`events-idempotency-errors.md`) — the `isinstance` check there already resolves it to
HTTP 409.

**What the caller does with it — matching `bold`'s own documented answer, not a blind
retry**: an HTTP entrypoint lets the 409 propagate to the client, which re-fetches current
state and reissues the request — the version field means a stale write fails loudly instead
of silently corrupting data. An event consumer may retry automatically *only* if re-running
the whole handler from a fresh `uow.repo(Stock).get(...)` is safe to repeat — which it is
here, because the idempotency check (`events-idempotency-errors.md`) already guards the
outer transaction, so a retry after `ConcurrentModificationError` is exactly as safe as
SQS's own at-least-once redelivery already assumes.

**Where this applies:** only on `AggregateRoot`, not on every `Entity` — a child entity
inside an aggregate (`OrderLine`) has no independent existence to race over; its consistency
is already covered by its owning aggregate root's version.
