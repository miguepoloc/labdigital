# Domain layer and application layer

> Topic excerpt of `../../../ARCHITECTURE.md` §5–§6. If this file and `ARCHITECTURE.md`
> disagree, `ARCHITECTURE.md` wins. Section numbers below (§5.1, §6, ...) match that
> document's numbering — use them to jump to the fuller context there if needed.

**Contents**: §5.1 base types (`PosixTime`, `UuidV7Id`/`HumanFriendlyId`, `Entity`,
`AggregateRoot`) · §5.2 typed IDs · §5.3 aggregates · §5.4 business rules · §5.5 domain
exceptions · §5.6 ports · §5.7 `Money` · §6 application layer (`services/`).

## §5. Domain layer

### §5.1 Base types (from `commons.domain`)

```python
# commons/domain/value_objects.py
import datetime
import uuid

from commons.domain import base_model


class ValueObject(base_model.DomainModel):
    """Immutable, defined by its value — never has an id."""
    model_config = {"frozen": True}


class PosixTime(ValueObject):
    """POSIX timestamp in integer microseconds since epoch, UTC.

    Never store or pass a native `datetime` across a domain boundary. Mixing
    timezone-aware and timezone-naive datetimes is a well-known, recurring bug class;
    an integer epoch admits no such ambiguity, and it maps directly onto a `BigInteger`
    database column (see persistence-and-concurrency.md) with no driver-level timezone
    conversion to get wrong.
    """
    microseconds: int

    @classmethod
    def now(cls) -> "PosixTime":
        return cls.from_datetime(datetime.datetime.now(tz=datetime.UTC))

    def __lt__(self, other: "PosixTime") -> bool:
        return self.microseconds < other.microseconds

    def __le__(self, other: "PosixTime") -> bool:
        return self.microseconds <= other.microseconds

    def __gt__(self, other: "PosixTime") -> bool:
        return self.microseconds > other.microseconds

    def __ge__(self, other: "PosixTime") -> bool:
        return self.microseconds >= other.microseconds

    @classmethod
    def from_datetime(cls, value: datetime.datetime) -> "PosixTime":
        return cls(microseconds=int(value.timestamp() * 1_000_000))
```

**Use these comparison operators — never unwrap `.microseconds` to compare by hand.**
`sona-sso-backend`'s own `PosixTime` has this same operator set, and `sona-sso-backend`'s
own `entrypoints/cron/check_cert_expiry.py` still reaches into
`connection.cert_expires_at.microseconds` for a manual comparison instead of using it — the
canonical negative example, see `anti-patterns-and-design-principles.md`. Compare
`if cert.expires_at < PosixTime.now():` against
`if cert.expires_at.microseconds < PosixTime.now().microseconds:` — same result, but the
second line has silently thrown away the type safety `PosixTime` exists to provide (nothing
stops it from being compared against a raw `int` that isn't even a timestamp). The ORM
mapper's `_to_orm`/`_to_entity` functions (`persistence-and-concurrency.md`) are the one
place `.microseconds` is unwrapped, because that translation is their entire reason to
exist — not a loophole to reuse elsewhere.

```python
class UuidV7Id(ValueObject):
    """Default typed-ID base. Time-ordered, good for B-tree indexes."""
    value: uuid.UUID

    @classmethod
    def new(cls) -> "UuidV7Id":
        return cls(value=uuid_extensions.uuid7())


class HumanFriendlyId(ValueObject):
    """Use only when the ID is user-facing (appears in a URL, a support ticket)."""
    value: str

    @classmethod
    def new(cls) -> "HumanFriendlyId":
        return cls(value=id_generator.generate_short_id())
```

```python
# commons/domain/entities.py
from commons.domain import base_model, value_objects


class Entity[IdT](base_model.DomainModel):
    id: IdT
    created_at: value_objects.PosixTime
    updated_at: value_objects.PosixTime

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.id == other.id
```

```python
# commons/domain/aggregates.py
import pydantic

from commons.domain import entities
from commons.domain import events as domain_events


class AggregateRoot[IdT](entities.Entity[IdT]):
    version: int = 0   # optimistic concurrency — see persistence-and-concurrency.md
    _events: list[domain_events.DomainEvent] = pydantic.PrivateAttr(default_factory=list)

    def record_event(self, event: domain_events.DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[domain_events.DomainEvent]:
        pulled, self._events = self._events, []
        return pulled
```

`domain_events` is an alias, not decoration — without it, the local variable/parameter name
`event`/`events` used throughout this file would shadow the module name (see
`enforcement-and-style.md`'s import rule).

`record_event`/`pull_events` behavior is taken directly from `bold`'s `AggregateEventAware`.
**Rule, non-negotiable:** if a subcontext calls `record_event`, its `services/<subcontext>.py`
must call `pull_events()` and write the result to the outbox (`events-idempotency-errors.md`)
inside the same transaction. `sona-sso-backend` shipped the alternative — silently — to
production; don't repeat it.

**Why `Entity[IdT]`/`AggregateRoot[IdT]` are generic, when `bold`'s aren't.** `bold`'s real
`base_types.Entity` is *not* generic — `id: "EntityId"` — and every concrete aggregate just
redeclares `id: CashinId` (a subtype), with no apparent issue. That works for `bold` because
it type-checks with `mypy` against Pydantic v1, which doesn't flag narrowing a mutable
field's type in a subclass. `sona-sso-backend` hit a real error doing the equivalent under
`pyright` (which does flag it — narrowing a mutable attribute's type in a subclass is an
actual Liskov violation: code holding a bare `Entity` reference could assign
`entity.id = SomeOtherId()`, which a `Stock` narrowed to `id: StockId` would not survive).
This standard uses `pyright` and Pydantic v2, so it inherits that stricter check — PEP 695
generics are the fix that requires zero `# type: ignore` anywhere, chosen deliberately over
`bold`'s simpler-but-narrower-typed approach for exactly that reason. If a future maintainer
switches this standard to `mypy`-only type checking, this trade-off is worth revisiting — the
generic machinery stops paying for itself the moment nothing enforces the violation it exists
to avoid.

### §5.2 Typed IDs

One wrapper type per aggregate, chosen **once, per aggregate type, at definition time**,
never per instance:

```python
# commerce/stock/domain/model/value_objects.py
from commons.domain import value_objects


class StockId(value_objects.UuidV7Id):
    pass
```

```python
# commerce/orders/domain/model/value_objects.py
from commons.domain import value_objects

from commerce.commons import value_objects as commerce_value_objects


class OrderId(value_objects.HumanFriendlyId):
    pass


class OrderLine(value_objects.ValueObject):
    sku: commerce_value_objects.Sku   # shared across orders/ and stock/ — a product-local
                                       # commons/ VO, see shared-kernel-and-testing.md
    quantity: int
```

Default to `UuidV7Id`; use `HumanFriendlyId` only when the ID is genuinely user-facing — and
`OrderId` above is exactly that case: a customer reads this ID off a receipt, quotes it in a
support call, or it's printed on a packing slip. Verified against bold's real selection:
`LoanId` and `BancolombiaCardlessCashout`'s `CashoutId` — both "a specific transaction a
customer would reference by ID" — are `base_types.HumanFriendlyId`; `StockId` above stays
`UuidV7Id` because `Stock` is never shown to a customer directly (`Sku` is the human-facing
identifier there).

**`identity.users.UserId` is `HumanFriendlyId` too** — verified against `sona-sso-backend`'s
real identity aggregates (`ConsoleUserId`, `OrganizationId`, `SsoConnectionId`, all
`HumanFriendlyId`), not bold's fintech-transaction ones: a user's id appears in admin/support
tooling URLs and audit logs a human reads, the same case as `Order`. **That cascades**:
`commerce.orders.CustomerId` mirrors `UserId`'s real value (`on_user_deactivated.py`
reconstructs a `CustomerId` directly from `UserDeactivated.user_id.value`,
`entrypoints-and-orchestration.md` §10.3), so it must share `UserId`'s value shape even while
staying an independently-declared type — it moved to `HumanFriendlyId` in lockstep, not as an
independent choice. Nothing in the type system catches this on its own:
`CustomerId(value: uuid.UUID)` type-checks fine right up until a real `HumanFriendlyId`
string reaches `uuid.UUID(...)` and raises `ValueError` at runtime.

A `HumanFriendlyId`-keyed repository's insert must retry on collision — see
`commons.adapters.repository_helpers.insert_with_id_retry` (`persistence-and-concurrency.md`
§7.1).

### §5.3 Aggregates

```python
# commerce/stock/domain/model/aggregate.py
from commons.domain import aggregates

from commerce.commons import value_objects as commerce_value_objects
from commerce.stock.domain.model import events, exceptions, value_objects


class Stock(aggregates.AggregateRoot[value_objects.StockId]):
    sku: commerce_value_objects.Sku
    available_quantity: int

    @classmethod
    def create(
        cls, *, sku: commerce_value_objects.Sku, initial_quantity: int,
    ) -> "Stock":
        stock = cls(id=value_objects.StockId.new(), sku=sku,
                    available_quantity=initial_quantity)
        stock.record_event(events.StockCreated(stock_id=stock.id, sku=sku))
        return stock

    def reserve(self, quantity: int) -> None:
        if self.available_quantity < quantity:
            raise exceptions.InsufficientStockError(
                sku=self.sku, requested=quantity, available=self.available_quantity,
            )
        self.available_quantity -= quantity
        self.touch()
        self.record_event(events.StockReserved(stock_id=self.id, sku=self.sku,
                                                 quantity=quantity))

    def release(self, quantity: int) -> None:
        self.available_quantity += quantity
        self.touch()
        self.record_event(events.StockReleased(stock_id=self.id, sku=self.sku,
                                                  quantity=quantity))
```

Conventions, cross-validated against `bold`'s `breb_cashin` aggregate:

- **Class-method factories** (`create`, or `create_<state>` for multiple valid starting
  states) construct-and-record-event in one place.
- **Instance methods are commands**, named as verbs (`reserve`, `confirm`, `cancel`), never
  generic setters. Each: (1) guards with a check raising a **narrow, named** domain
  exception, (2) mutates state, (3) calls `self.touch()` if state actually changed, (4)
  records exactly the events describing what happened.
- **No infrastructure here.** Not a repository, not a session, not an HTTP client. An
  external fact (a price, a rate) is a **parameter** supplied by the caller.

#### §5.3a `touch()` and the status-transitions dict

The `self.updated_at = PosixTime.now()` line above is real repetition, found by grepping
bold's own aggregates (set inline at the end of nearly every command method across dozens of
files, never generalized). `AggregateRoot` centralizes it into one method:

```python
# commons/domain/aggregates.py
class AggregateRoot[IdT](entities.Entity[IdT]):
    def touch(self) -> None:
        self.updated_at = value_objects.PosixTime.now()
```

A status-holding aggregate additionally declares a **module-level transitions dict** — the
same shape as bold's real `_BANCOLOMBIA_CARDLESS_CASHOUT_STATUS_TRANSITIONS: dict[Status,
list[Status]]` — and a private `_transition_status` method that is the *only* place the
status field is assigned:

```python
# commerce/orders/domain/model/aggregate.py
_ORDER_STATUS_TRANSITIONS: dict[value_objects.OrderStatus, list[value_objects.OrderStatus]] = {
    value_objects.OrderStatus.PENDING: [
        value_objects.OrderStatus.CONFIRMED, value_objects.OrderStatus.CANCELLED,
    ],
    value_objects.OrderStatus.CONFIRMED: [value_objects.OrderStatus.CANCELLED],
    value_objects.OrderStatus.CANCELLED: [],
}


class Order(aggregates.AggregateRoot[value_objects.OrderId]):
    def confirm(self, *, shipping_name: str, shipping_email: str) -> None:
        self._transition_status(
            new_status=value_objects.OrderStatus.CONFIRMED,
            invalid_transition_error=exceptions.OrderCannotBeConfirmedError(
                order_id=self.id, status=self.status,
            ),
        )
        self.shipping_name = shipping_name
        self.shipping_email = shipping_email
        self.record_event(events.OrderConfirmed(order_id=self.id))

    def _transition_status(
        self, *, new_status: value_objects.OrderStatus,
        invalid_transition_error: exceptions.DomainError,
    ) -> None:
        if new_status not in _ORDER_STATUS_TRANSITIONS[self.status]:
            raise invalid_transition_error
        self.status = new_status
        self.touch()
```

Unlike bold's `_change_status` (one generic `*UpdateStatusError` for every invalid
transition), this standard keeps §5.5's one-named-exception-per-invalid-transition
convention: the caller passes its own already-constructed exception in, so the `code` an API
consumer sees stays action-specific. The dict and `_transition_status` live on the aggregate
that owns the status field, not on the shared `AggregateRoot` — only `touch()` (identical
everywhere) belongs on the base class.

### §5.4 Business rules

```python
# commons/domain/business_rules.py
import abc

from commons.domain import exceptions


class BusinessRule(abc.ABC):
    @abc.abstractmethod
    def is_broken(self) -> bool: ...

    @abc.abstractmethod
    def message(self) -> str: ...

    def check(self) -> None:
        if self.is_broken():
            raise exceptions.ValidationError(self.message())
```

Use a named `BusinessRule` subclass for an invariant complex enough to deserve independent
testing and a name. Trivial invariants stay as an inline `if/raise` inside the aggregate
method — don't manufacture a `BusinessRule` class for every single guard clause.

### §5.5 Domain exceptions

One class per invalid transition (`bold`'s convention), not one generic exception
parameterized by a state string:

```python
# commerce/stock/domain/model/exceptions.py
from commons.domain import exceptions


class InsufficientStockError(exceptions.ConflictError):
    def __init__(self, *, sku: "commerce_value_objects.Sku", requested: int,
                 available: int) -> None:
        super().__init__(
            f"Cannot reserve {requested} of sku [{sku}]: only {available} available.",
            code="INSUFFICIENT_STOCK",
        )
```

`commons.domain.exceptions.DomainError` and its subclasses are defined once — see
`events-idempotency-errors.md`.

### §5.6 Ports

A **port** is an `abc.ABC` in `domain/model/ports.py`, declared by the domain because it
needs a capability the outside world provides (dependency inversion). Exists for exactly two
reasons — full decision tree in `entrypoints-and-orchestration.md`:

1. A synchronous call to a genuinely **external** system (a payment gateway, a tax API).
2. A synchronous call to **another bounded context's internal endpoint**, only to snapshot
   a point-in-time fact this aggregate must own a copy of (never to check
   permissions/existence — the JWT already proves that, see
   `entrypoints-and-orchestration.md`).

A port is never used to reach into another bounded context's database or domain model
directly.

### §5.7 Shared value types: `Money`

Ported (trimmed) from `bold.commons.standard_types.money`, the strongest example in any of
the three reference codebases of "a value object owns its own behavior": every operation a
caller could plausibly need — arithmetic, comparison, formatting, sign checks, splitting a
total across rates, rounding — lives on the value object itself, so no caller anywhere ever
reaches into `.value`/`.currency` to reimplement one of these by hand.

```python
# commons/domain/money.py
import decimal
import enum

from commons.domain import enums, exceptions, value_objects


class Currencies(enums.UpperStrEnum):   # UpperStrEnum, not plain StrEnum — see
    COP = enum.auto()                    # enforcement-and-style.md §17.3; ISO-4217 codes
    USD = enum.auto()                    # are uppercase, .value == "COP"
    # ... full ISO-4217 set in bold's original; trim to what the product needs.


class Money(value_objects.ValueObject):
    currency: Currencies
    value: decimal.Decimal

    def __add__(self, other: "Money") -> "Money":
        if self.currency is not other.currency:
            raise exceptions.ValidationError("Can't add different currencies")
        return Money(currency=self.currency, value=self.value + other.value)

    def __mul__(self, other: int | decimal.Decimal) -> "Money":
        return Money(currency=self.currency, value=self.value * decimal.Decimal(other))

    def compare(self, other: "Money") -> decimal.Decimal:
        if self.currency is not other.currency:
            raise exceptions.ValidationError("Can't compare different currencies")
        return self.value.compare(other=other.value)

    def __lt__(self, other: "Money") -> bool:
        return self.compare(other) < 0

    def is_zero(self) -> bool:
        return self.value.is_zero()

    @classmethod
    def cop(cls, value: decimal.Decimal) -> "Money":
        return cls(currency=Currencies.COP, value=value)


class NonNegativeMoney(Money):
    """Does not accept negative values."""
    value: decimal.Decimal  # constrained via pydantic.Field(ge=0) in the real definition


class PositiveMoney(Money):
    """Does not accept negative or zero values."""
    value: decimal.Decimal  # constrained via pydantic.Field(gt=0) in the real definition
```

**Golden-path usage**: `OrderLine.unit_price: money.PositiveMoney` is populated once, at
order-creation time, from the external pricing port (`entrypoints-and-orchestration.md`) —
that port's purpose is fetching the current price for a SKU and letting `Order` snapshot it,
for exactly the same reason the internal port snapshots the customer's profile (a later
price change must not rewrite historical orders). `Order.total` is a **computed `@property`**,
never a stored field:

```python
# commerce/orders/domain/model/aggregate.py  (excerpt)
class Order(aggregates.AggregateRoot[value_objects.OrderId]):
    lines: list[value_objects.OrderLine]
    status: value_objects.OrderStatus

    @property
    def total(self) -> money.Money:
        line_totals = (line.unit_price * line.quantity for line in self.lines)
        return sum(line_totals, start=money.Money(currency=self.lines[0].unit_price.currency,
                                                    value=decimal.Decimal(0)))
```

A stored `total` field would be a second source of truth that could drift from the lines it
should equal; a `@property` recomputes it from the lines every time — the correct default
for anything fully derived from other fields already on the aggregate.

---

## §6. Application layer (`services/`)

Called `services/`, matching both `bold` and `sona-sso-backend` (not `service_layer/`, not
`application/`).

```python
# commerce/stock/services/stock.py
from commons.adapters import logs

from commerce.stock.domain.model import aggregate
from commerce.stock.services import dto

_LOGGER = logs.get_logger()


def create_stock(*, uow: "unit_of_work.UnitOfWork",
                  input_dto: dto.CreateStockInputDTO) -> dto.StockOutputDTO:
    with uow.transaction():
        stock = aggregate.Stock.create(sku=input_dto.sku,
                                        initial_quantity=input_dto.initial_quantity)
        uow.repo(aggregate.Stock).add(stock)
    _LOGGER.info("Stock created for sku [%s]", stock.sku)
    return dto.StockOutputDTO.from_entity(stock)


def reserve_stock(*, uow: "unit_of_work.UnitOfWork", sku: "commerce_value_objects.Sku",
                   quantity: int) -> None:
    with uow.transaction():
        stock_repo = uow.repo(aggregate.Stock)   # resolved once, reused for get + update
        stock = stock_repo.get_by_sku(sku)
        stock.reserve(quantity)                  # raises InsufficientStockError → rollback
        stock_repo.update(stock)
```

No `_publish_events()` helper here — `DefaultStockRepository.add`/`.update` drain and record
the entity's events internally, in the same transaction as the write
(`persistence-and-concurrency.md` §7). Rules:

- One function per use case, named as a verb (`create_stock`, `reserve_stock`), not
  `StockService.create`. Group related use-case functions in one module per subcontext
  (`stock.py`); split into more files only once a subcontext genuinely has enough of them.
- **Always** takes `uow` as an explicit parameter — no invisible framework DI inside the
  function. FastAPI's `Depends()` wires it at the entrypoint
  (`entrypoints-and-orchestration.md`); the function itself is plain, framework-agnostic,
  testable with a fake UoW.
- **This module is the only place in the whole codebase allowed to call
  `uow.repo(aggregate.Stock)` or `stock.reserve(...)`.** An orchestrator calls
  `reserve_stock(...)`, never the aggregate directly — see
  `entrypoints-and-orchestration.md` for why, verified against `bold`'s real orchestrators.
- **`uow.repo(aggregate.Stock)` must be called from inside `with uow.transaction():`, never
  before it opens** — `UnitOfWork.repo` reads `UnitOfWork.session`, which raises
  `RuntimeError` until a transaction is open (`persistence-and-concurrency.md` §8).
- A function using its repository more than once (a `.get` then an `.update`, say) resolves
  it **once** and reuses the local variable — not a correctness issue (the UoW memoizes the
  instance either way), but two separate-looking calls read as two separate concerns where
  there's only one.
