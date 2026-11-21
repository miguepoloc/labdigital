# Backend Architecture Standard

**FastAPI + PostgreSQL + AWS Lambda, built on Domain-Driven Design and Hexagonal Architecture.**

This document is the single source of truth for how backend services are built in this
standard. It is written to be read by both humans and AI coding agents. If you are an AI
agent implementing a feature, this document tells you exactly where every piece of code
goes, what it's called, what it may and may not depend on, and why. When this document and
the code disagree, the code is out of date — fix the code or fix this document, but do not
silently diverge.

## 0. Provenance — where this standard comes from

This is not a theoretical design. It is a deliberate synthesis of:

- **[`bold/deposit`](#appendix-source-material)** — the most mature, most-organized bounded
  context at Bold (fintech). Real production code handling money movement across ~90
  sub-modules. Source of: the two-level `product/subcontext` layout (plus product-local
  `commons/`, §3.2), the generic `UnitOfWork` + repository-registry pattern, the
  **orchestrator-calls-services-never-aggregates** layering rule (§10, verified directly
  against `breb_cashin_management.py` and its orchestrators), domain vs. integration event
  separation, event-level idempotency keys, module-qualified imports (§17.1, verified
  directly against real source), and the "screaming architecture" naming rule.
- **`sona-sso-backend`** — a FastAPI + PostgreSQL + SQLAlchemy + Lambda service, the closest
  real precedent to this standard's target stack. Source of: sync SQLAlchemy over async, the
  `Idempotency-Key` HTTP header pattern, typed IDs via PEP 695 generics, the `DomainError`
  hierarchy, import-linter contracts, `PosixTime` (microsecond epoch, §5.1 — verified
  directly against `commons/domain/value_objects.py`), the `TimestampsMixin`/`BigInteger`
  timestamp-storage rule (verified against `commons/adapters/orm_base.py`), and the single
  cached structured-JSON logger (`commons.logs.get_logger()`, verified directly against
  `commons/logs.py`). Also the source of a cautionary tale (§20): its domain events are
  recorded but never drained.
- **`sona` (serverless v1)** — a working SNS→SQS fan-out event architecture across ~30
  Lambdas. Source of: one API Lambda per bounded context, one event-handler Lambda per
  (context, topic) pair, and the "fakes over mocks" testing convention. Also a cautionary
  tale: no idempotency layer for event consumers, three coexisting generations of shared code.
- **[_Architecture Patterns with Python_ (Cosmic Python), Percival & Gregory](https://www.cosmicpython.com/)**
  — vocabulary and reasoning (Repository, Unit of Work, Aggregate, consistency boundaries,
  ports and adapters, dependency inversion). Where this standard deliberately diverges, it
  says so and explains why (§10.4).
- **[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)** — naming,
  docstrings, typing, formatting, and — load-bearing throughout this whole document —
  **"imports should be used for packages and modules only, not for individual classes or
  functions"** (§17.1). This rule is applied to every code sample below; it is not
  decorative.

None of the three real codebases implements this whole stack correctly end-to-end. This
document is the corrected, unified version: the best-evidenced pattern for each concern,
verified against real source (not remembered from a summary) wherever a correction was
needed, with the alternatives explained.

---

## 1. Guiding principles

1. **The domain model owns the business rules and knows nothing about the outside world.**
   No `fastapi`, `sqlalchemy`, `boto3`, or `httpx` import ever appears under a `domain/`
   package. Enforced by CI (§16), not just convention.
2. **Dependencies point inward.** Entrypoints depend on services, services depend on domain
   and on ports. The domain depends on nothing in this codebase except `commons.domain`.
3. **A folder is named after the concept it contains, not a category that wraps it.**
   `stock/` contains `Stock`. `orders/` contains `Order`. See §3.1.
4. **Consistency boundaries are a business decision, not a technical default.** Two things
   that must always change together belong in one aggregate. Two things with independent
   reasons to change belong in separate aggregates, coordinated by an orchestrator (§10).
5. **Orchestrators call services. Services call aggregates and repositories. Never skip a
   layer.** An orchestrator that reaches past a service straight into `uow.repo(...)` or an
   aggregate method has re-implemented what the service layer is for, twice, in two places.
   This is not a style preference — it's how `bold` structures every real orchestrator in
   production, verified directly against source (§10).
6. **Every event that is recorded must be drained somewhere, or it must not be recorded.**
   `sona-sso-backend` records domain events on every mutation and never reads them back.
   This standard treats "record without a documented drain point" as a defect, not a
   phase-2 TODO.
7. **At-least-once delivery is the default assumption for anything that leaves a Postgres
   transaction.** Every event consumer, and every mutating HTTP endpoint a client might
   retry, is idempotent by construction (§12).
8. **Timestamps are `PosixTime` (integer microseconds since epoch), never a native
   `datetime`, anywhere — domain or database.** Mixing timezone-aware and timezone-naive
   `datetime` objects is a well-known, recurring source of silent date bugs; an integer
   epoch admits no ambiguity. See §5.1 and §7.
9. **Import modules, not names.** `from commerce.stock.domain.model import aggregate`, then
   `aggregate.Stock`, never `from commerce.stock.domain.model.aggregate import Stock`. This
   is a direct Google Python Style Guide rule, and it is exactly what `bold`'s real source
   does, file after file, verified directly. See §17.1 for the full rule and its narrow,
   named exceptions.
10. **Simplicity is a feature.** No message bus, no Command objects, no CQRS, no saga
    framework unless a concrete requirement demands it. Direct, typed function calls are the
    default.
11. **A value object owns its own behavior — reach into its internal field only at the ORM
    mapping seam, nowhere else.** `Money` (§5.7) exposes `__add__`, `__lt__`, `compare()`;
    `PosixTime` (§5.1) exposes `__lt__`/`__gt__`. Domain and application code call those, it
    never unwraps `.value`/`.microseconds` to reimplement them by hand — a real instance of
    exactly that mistake, found in `sona-sso-backend`'s own `check_cert_expiry.py`, is
    documented in §20 as the negative example. `adapters/repository.py`'s `_to_orm`/
    `_to_entity` functions are the one authorized exception (§7) — a Data Mapper's entire
    job is reaching across the domain/persistence boundary.

---

## 2. Tech stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.13 | Matches the most recent real precedent (`sona-sso-backend`); PEP 695 generics used for typed IDs. |
| Package manager | `uv` | Used by all three real codebases studied. |
| Web framework | FastAPI, deployed via **Mangum on AWS Lambda only** | No always-on server in this standard. This is what makes SQLAlchemy sync the correct choice (next row). |
| ORM / DB access | SQLAlchemy 2.0, **synchronous** | One Lambda invocation handles exactly one request; async buys nothing here and costs a per-invocation event loop plus `asyncio.to_thread` wrapping for boto3. `sona-sso-backend` migrated from async to sync for exactly this reason — start sync. |
| Database | PostgreSQL | — |
| Validation / serialization | Pydantic v2 | — |
| Migrations | Alembic, autogenerate-only (§18) | — |
| Lint + format | `ruff` | — |
| Type checking | `mypy` (or `pyright`) in CI | — |
| Architecture enforcement | `import-linter` | Contracts in §16 — not optional tooling, it's how §1's rules are actually enforced. |
| Testing | `pytest` + `testcontainers` for Postgres | §15 |
| Event delivery | Transactional Outbox → SNS/EventBridge → SQS | §11 |
| Logging | One cached, structured (JSON) logger per process, via `commons.adapters.logs.get_logger()` | §17.2 — never `logging.getLogger(__name__)` per file; see the reasoning there. |
| Outbound HTTP retries | `backoff` (`@backoff.on_exception(backoff.expo, ..., jitter=backoff.full_jitter, max_tries=3)`) | §10.2a — bold's real, exact configuration on every port-implementing adapter's external call; never a hand-rolled retry loop. |
| Email format validation | `pydantic.EmailStr` (`email-validator` package) | §17.3 — bold's own real, widespread choice on over a dozen DTOs/models; never a hand-rolled regex. |
| Configuration | `pydantic_settings.BaseSettings` (one `Settings` class, `commons/adapters/settings.py`) | §14.1 — verified against `sona-sso-backend`'s real `commons/settings.py`; every env var validated once, at `get_settings()`, never a scattered `os.environ[...]` read. |

### 2.1 `# type: ignore` discipline

`mypy.ini` sets `plugins = pydantic.mypy` (with `init_typed = True`) and, load-bearing here,
**`warn_unused_ignores = True`** — a `# type: ignore` that stops being necessary becomes a
build failure, not silently stale code. That config makes the discipline enforceable, but
the discipline itself is: **a `# type: ignore` is a last resort, tried only after the actual
type is fixed and still doesn't check.** The template's own history is the evidence this
gets followed, not just stated — every `# type: ignore` that turned out fixable *was* found
and fixed, once actually looked at instead of accepted as the cost of a generic parameter:

- `sns_client: object` in the outbox relay, `.publish(...)` flagged `[attr-defined]` — fixed
  by typing it `mypy_boto3_sns.client.SNSClient` (the stub the `boto3-stubs[sns]` dev
  dependency already provides) instead of the untyped escape hatch `object` was.
- `_REPO_REGISTRY: dict[..., type[Repository[Any]]]`, `repo_type(self.session)` flagged
  `[call-arg]` — the ABC declares no `__init__`, so mypy had no way to know a concrete
  repository takes a `Session`. Retyping the registry's values as
  `Callable[[Session], Repository[Any]]` (a class reference IS one, structurally) states the
  real contract directly; no ignore needed.
- `_HumanFriendlyIdRow` `Protocol` describing only `__tablename__`, `row.id` access flagged
  `[attr-defined]` twice — adding `id: str` to the Protocol (accurate: every
  `HumanFriendlyId`-keyed ORM row has a `str` id) was enough; SQLAlchemy 2.0's `Mapped[str]`
  satisfies a plain `id: str` structurally, no SQLAlchemy mypy plugin required.
- `EventConsumer.handle: Callable[[UoW, EventT], None] | Callable[[EventT], None]`,
  dispatched by inspecting `len(inspect.signature(consumer.handle).parameters)` at runtime —
  two call sites needed `[call-arg]`/`[arg-type]` ignores because mypy genuinely cannot
  narrow a union of different-arity callables from a runtime check. This one **was** a real
  design problem, not just a missing type annotation — fixed in §9.4 by splitting into two
  mutually-exclusive fields (`handle`/`handle_without_uow`), each a single concrete callable
  type. No ignore needed, and the fix is a real improvement independent of mypy: the
  registration call site now states its intent (`handle=` vs `handle_without_uow=`) instead
  of the dispatcher inferring it from argument count.

**One ignore remains, and stays** — `@pydantic.computed_field  # type: ignore[prop-decorator]`
on `DomainEvent.event_type` (§11.1). Verified directly (not assumed): mypy raises
`Decorators on top of @property are not supported` for `@computed_field` stacked on
`@property` even with the pydantic plugin active and even calling `@computed_field()` with
parens — this is pydantic's own documented workaround for a real mypy limitation, not
something a local type fix or plugin config can resolve. The difference between this one and
the four above is exactly the test to apply before writing any `# type: ignore`: has the
actual type been fixed and still doesn't check (keep the ignore, narrowly scoped, and say
why), or was the type just never actually attempted (fix the type)?

---

## 3. Repository layout

A **monorepo housing multiple bounded contexts**, grouped into **products**, each possibly
containing several **subcontexts**. Two-level nesting (`product/subcontext/`) is used
**uniformly**, even when a product has only one subcontext today.

```
.
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── mypy.ini
├── ruff.toml
├── .importlinter               # architecture contracts, see §16
├── docker-compose.yml
├── Makefile
├── src/
│   └── backend/
│       ├── commons/              # GLOBAL shared kernel — see §14. Never imports a product.
│       │   ├── domain/
│       │   │   ├── base_model.py
│       │   │   ├── entities.py
│       │   │   ├── aggregates.py
│       │   │   ├── value_objects.py     # ValueObject, PosixTime, UuidV7Id, HumanFriendlyId
│       │   │   ├── money.py             # Money, NonNegativeMoney, PositiveMoney — see §5.7
│       │   │   ├── events.py
│       │   │   ├── business_rules.py
│       │   │   ├── exceptions.py
│       │   │   └── repositories.py
│       │   ├── application/
│       │   │   └── dto.py
│       │   └── adapters/
│       │       ├── engine.py
│       │       ├── orm_base.py            # Base, TimestampsMixin, Idempotency/Outbox/ProcessedEvent tables
│       │       ├── unit_of_work.py
│       │       ├── repository_helpers.py
│       │       ├── outbox.py
│       │       ├── sqs.py                 # EventConsumer, process_sqs_event() — §9.4
│       │       ├── authentication.py
│       │       ├── logs.py                # get_logger() — see §17.2
│       │       └── api/
│       │           ├── exception_handler.py
│       │           └── middleware.py
│       ├── orchestrators/         # CROSS-BOUNDED-CONTEXT orchestration only. See §10.3.
│       │   └── __init__.py        # empty in this golden path — §10.3 explains why
│       ├── identity/               # === PRODUCT ===
│       │   ├── users/                # === SUBCONTEXT === (contains aggregate `User`)
│       │   │   ├── domain/
│       │   │   │   ├── model/
│       │   │   │   │   ├── aggregate.py
│       │   │   │   │   ├── value_objects.py
│       │   │   │   │   ├── events.py
│       │   │   │   │   ├── exceptions.py
│       │   │   │   │   ├── rules.py
│       │   │   │   │   └── ports.py
│       │   │   │   └── services/
│       │   │   ├── adapters/
│       │   │   │   ├── orm.py
│       │   │   │   └── repository.py
│       │   │   ├── services/
│       │   │   │   ├── auth.py
│       │   │   │   ├── dto.py
│       │   │   │   └── ports.py
│       │   │   └── tests/{unit,integration}/
│       │   └── entrypoints/
│       │       ├── web/{public,internal}.py
│       │       ├── events/
│       │       └── cron/expire_refresh_tokens.py
│       │
│       └── commerce/               # === PRODUCT ===
│           ├── commons/              # PRODUCT-LOCAL shared kernel — see §3.2. Shared only
│           │   │                    # by commerce's own subcontexts, never imported from
│           │   │                    # outside commerce/, never imports the global commons'
│           │   │                    # position (it sits BELOW global commons, ABOVE subcontexts).
│           │   └── value_objects.py   # Sku — used by both orders/ and stock/
│           ├── orders/                # === SUBCONTEXT === (contains aggregate `Order`)
│           │   ├── domain/model/{aggregate,value_objects,events,exceptions,rules,ports}.py
│           │   ├── adapters/{orm,repository,payment_adapter}.py
│           │   ├── services/{orders,dto}.py
│           │   └── tests/{unit,integration}/
│           ├── stock/                 # === SUBCONTEXT === (contains aggregate `Stock`)
│           │   ├── domain/model/{aggregate,value_objects,events,exceptions,rules}.py
│           │   ├── adapters/{orm,repository}.py
│           │   ├── services/{stock,dto}.py
│           │   └── tests/{unit,integration}/
│           ├── services/               # PRODUCT-LEVEL orchestration (cross-subcontext, same product)
│           │   └── confirm_order_orchestrator.py   # calls orders/stock SERVICES, §10.2
│           └── entrypoints/
│               ├── web/{public,internal}.py
│               ├── events/on_user_deactivated.py
│               └── cron/expire_pending_orders.py
├── migrations/
└── tests/e2e/
```

### 3.1 The naming rule, precisely

A **subcontext folder name matches the aggregate it contains**, in `snake_case`:
`orders/` → `Order`, `stock/` → `Stock`, `users/` → `User` — mirrors `bold`'s
`breb_cashin/` → `BreBCashin`. A **product folder name is the umbrella capability**
(`identity`, `commerce`); it corresponds to no single aggregate.

### 3.2 Product-local `commons/` — a real gap this standard almost missed

`bold`'s real source contains not only the global `bold.commons` but also product-local
shared modules, e.g. `bold.deposit.breb.commons` (imported as
`from bold.deposit.breb.commons import value_objects as commons_value_objects` inside
`breb_cashin_management.py`) — a shared-vocabulary layer for concepts used by several
subcontexts of the **same** product, but not general enough for the global `commons/`.

This standard adopts the same middle tier: `<product>/commons/`. Rule: a value object or
type used by two or more subcontexts of one product (e.g. `Sku`, needed by both
`commerce/orders` and `commerce/stock`) lives in `<product>/commons/`, **not** duplicated in
each subcontext, and **not** promoted to the global `commons/` unless a *second product*
also needs it. This also closes a real hole in import-linter contract 3 (§16): a subcontext
importing a sibling subcontext's `domain/` directly is forbidden, but importing its own
product's `commons/` is explicitly allowed.

---

## 4. Bounded context anatomy

```
<product>/<subcontext>/
├── domain/
│   ├── model/
│   │   ├── aggregate.py      # REQUIRED. The aggregate root and any owned child entities.
│   │   ├── value_objects.py  # REQUIRED. Immutable VOs local to this aggregate.
│   │   ├── events.py         # REQUIRED if the aggregate raises events (almost always).
│   │   ├── exceptions.py     # REQUIRED. One class per invalid state transition.
│   │   ├── rules.py          # OPTIONAL. Named BusinessRule subclasses (§5.4).
│   │   └── ports.py          # OPTIONAL. Only for a SYNCHRONOUS outbound dependency (§10.2).
│   └── services/             # OPTIONAL. Pure domain services — no I/O except via a port.
├── adapters/
│   ├── orm.py                # REQUIRED. SQLAlchemy mappings. Infra-only.
│   ├── repository.py         # REQUIRED. Implements Repository[T]; `_to_orm`/`_to_entity`.
│   └── <external>_adapter.py # OPTIONAL. One per external system called synchronously.
├── services/                  # APPLICATION layer — the ONLY thing entrypoints AND
│   │                         # orchestrators are allowed to call into this subcontext with.
│   ├── <subcontext>.py        # REQUIRED. Use-case functions. Owns `uow.repo(Aggregate)`
│   │                         # calls, owns aggregate-method calls, owns event draining.
│   ├── dto.py                 # REQUIRED. Input/output DTOs, output owns `.from_entity()`.
│   └── ports.py               # OPTIONAL. A local UnitOfWork Protocol, rarely needed (§8).
└── tests/{unit,integration}/
```

**Rule, enforced by import-linter contract 6 (§16): nothing outside this subcontext's own
`services/` may import this subcontext's `domain/` or `adapters/`.** Not an entrypoint, not
a product-level orchestrator, not a cross-context orchestrator. If code outside
`services/<subcontext>.py` needs to touch this aggregate, it calls a function in
`services/<subcontext>.py` — that function is the *only* door in. (One narrow exception:
`domain/model/value_objects` may be imported elsewhere purely to type-hint a pass-through
parameter — never `aggregate`/`events`/`rules`/`adapters`. Full reasoning in §16.)

Product-level files (sibling to the subcontext folders):

```
<product>/
├── commons/                                # Optional — see §3.2.
├── services/
│   └── <verb>_<subject>_orchestrator.py     # Calls OTHER SUBCONTEXTS' services/ functions
│                                           # only. May open ONE uow.transaction() that
│                                           # those calls join (§8, §10.2). Never imports a
│                                           # subcontext's aggregate/events/rules/adapters,
│                                           # never calls uow.repo(...) itself — value_objects
│                                           # is the one exception, for typing only (§16).
└── entrypoints/
    ├── web/{public,internal}.py             # See §9.1/§9.2.
    ├── events/                              # See §9.4.
    └── cron/                                # See §9.5.
```

**How to read the code samples below.** Every snippet from here on follows §17.1's
module-import rule for what it actually imports. Not every snippet re-imports names already
established by an earlier, fuller example in this same document — a reference to a type not
imported in that snippet's own header is a genuine cross-reference, marked as a quoted
forward-reference (`"unit_of_work.UnitOfWork"`) rather than left unmarked, and resolved by
the nearest earlier full example of that module. This keeps each excerpt focused on the
concept it's illustrating instead of repeating a growing import block every time. The
template project (§19) is the ground truth with zero unresolved references — self-audited
against this document, and where a real gap was found (a missing `outbox` import in §8's
`UnitOfWork`), it was fixed here directly rather than left for the template to silently
diverge from.

---

## 5. Domain layer

### 5.1 Base types (from `commons.domain`)

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

    Never store or pass a native `datetime` across a domain boundary (§1.8). Mixing
    timezone-aware and timezone-naive datetimes is a well-known, recurring bug class;
    an integer epoch admits no such ambiguity, and it maps directly onto a `BigInteger`
    database column (§7) with no driver-level timezone conversion to get wrong.
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
`connection.cert_expires_at.microseconds` for a manual comparison instead of using it — a
real instance of the exact mistake §1.11 exists to prevent, found in the wild while
verifying this document. Compare `PosixTime`'s own `if cert.expires_at < PosixTime.now():`
against `if cert.expires_at.microseconds < PosixTime.now().microseconds:` — same result,
but the second line has silently thrown away the type safety `PosixTime` exists to provide
(nothing stops it from being compared against a raw `int` that isn't even a timestamp).
`_to_orm`/`_to_entity` in `adapters/repository.py` (§7) are the one place `.microseconds`
is unwrapped, because that translation is their entire reason to exist — not a loophole to
reuse elsewhere.

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
    version: int = 0   # optimistic concurrency — see §8.1
    _events: list[domain_events.DomainEvent] = pydantic.PrivateAttr(default_factory=list)

    def record_event(self, event: domain_events.DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[domain_events.DomainEvent]:
        pulled, self._events = self._events, []
        return pulled
```

`domain_events` is an alias, not decoration — without it, the local variable/parameter name
`event`/`events` used throughout this file would shadow the module name (§17.1).

`record_event`/`pull_events` behavior is taken directly from `bold`'s `AggregateEventAware`.
**Rule, non-negotiable (§1.6):** if a subcontext calls `record_event`, its
`services/<subcontext>.py` must call `pull_events()` and write the result to the outbox
(§11) inside the same transaction. `sona-sso-backend` shipped the alternative — silently —
to production; don't repeat it.

**Why `Entity[IdT]`/`AggregateRoot[IdT]` are generic, when `bold`'s aren't.** `bold`'s real
`base_types.Entity` is *not* generic — `id: "EntityId"` — and every concrete aggregate just
redeclares `id: CashinId` (a subtype), with no apparent issue. That works for `bold` because
it type-checks with `mypy` against Pydantic v1, which doesn't flag narrowing a mutable
field's type in a subclass. `sona-sso-backend` hit a real error doing the equivalent under
`pyright` (which does flag it — narrowing a mutable attribute's type in a subclass is an
actual Liskov violation: code holding a bare `Entity` reference could assign
`entity.id = SomeOtherId()`, which a `Stock` narrowed to `id: StockId` would not survive).
This standard uses `pyright` (§2) and Pydantic v2, so it inherits that stricter check —
PEP 695 generics are the fix that requires zero `# type: ignore` anywhere, chosen
deliberately over `bold`'s simpler-but-narrower-typed approach for exactly that reason. If a
future maintainer switches this standard to `mypy`-only type checking, this trade-off is
worth revisiting — the generic machinery stops paying for itself the moment nothing enforces
the violation it exists to avoid.

### 5.2 Typed IDs

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
    sku: commerce_value_objects.Sku   # shared across orders/ and stock/, see §3.2
    quantity: int
```

Default to `UuidV7Id`; use `HumanFriendlyId` only when the ID is genuinely user-facing — and
`OrderId` is exactly that case, not `UuidV7Id` (an earlier draft of this document had it
backwards, contradicting its own rule in the very example meant to illustrate it: a customer
reads this ID off a receipt, quotes it in a support call, or it's printed on a packing slip.
Verified against bold's real selection: `LoanId` and `BancolombiaCardlessCashout`'s
`CashoutId` — both "a specific transaction a customer would reference by ID" — are
`base_types.HumanFriendlyId`. `StockId` above stays `UuidV7Id`: `Stock` is never shown to a
customer directly, `Sku` is the human-facing identifier there.

**`identity.users.UserId` is `HumanFriendlyId` too** — verified against `sona-sso-backend`'s
real identity aggregates specifically, not bold's fintech-transaction ones: `ConsoleUserId`,
`OrganizationId`, `SsoConnectionId` are all `HumanFriendlyId` in the one reference codebase
that's actually an identity backend. A user's id appears in admin/support tooling URLs and
audit logs a human reads — the same "genuinely user-facing" case as `Order`, a login flow
being email-first doesn't change that. An earlier draft of this document left `UserId` as
`UuidV7Id`, reasoning "a user is identified by email, not by id" — true for *login*, not for
every other place a human ends up reading the id.

**That choice cascades**: `commerce.orders.CustomerId` mirrors `UserId`'s real value —
`commerce/entrypoints/events/on_user_deactivated.py` reconstructs a `CustomerId` directly
from `UserDeactivated.user_id.value` to find that customer's orders (§10.3), so the two must
share a value *shape* even while staying independently-declared types (§10.3's own
decoupling reasoning). `CustomerId` moved to `HumanFriendlyId` in lockstep with `UserId` —
not an independent decision, and not something mypy catches on its own: `CustomerId(value:
uuid.UUID)` type-checks perfectly fine on its own, right up until a real (non-UUID-shaped)
`HumanFriendlyId` string reaches `uuid.UUID(...)` at runtime and raises `ValueError`. Found
by tracing the `UserId` change through its consumers, not by any tool — "these two
independently-declared types must share a value format" is a domain constraint with nothing
in the type system to enforce it.

A `HumanFriendlyId`-keyed repository's insert must retry on collision — see
`commons.adapters.repository_helpers`, module imported the same way: `from commons.adapters
import repository_helpers`, called as `repository_helpers.insert_with_id_retry(session,
row)` (§7's `Repository[T].add` is where this actually gets called; `UuidV7Id`-keyed
aggregates never need it).

### 5.3 Aggregates

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

#### 5.3a `touch()` and the status-transitions dict

Every command above ends with a `self.updated_at = PosixTime.now()` line — that's real
repetition, found by grepping bold's own aggregates (`updated_at`/`last_update_date` is set
inline at the end of nearly every command method across dozens of files). Bold never
generalized it into a base-class helper; this standard does, since the line is genuinely
identical everywhere it appears:

```python
# commons/domain/aggregates.py
class AggregateRoot[IdT](entities.Entity[IdT]):
    version: int = 0
    _events: list[domain_events.DomainEvent] = pydantic.PrivateAttr(default_factory=list)

    def touch(self) -> None:
        self.updated_at = value_objects.PosixTime.now()
```

A status-holding aggregate additionally declares a **module-level transitions dict** — the
same shape as bold's real
`_BANCOLOMBIA_CARDLESS_CASHOUT_STATUS_TRANSITIONS: dict[Status, list[Status]]` in
`bancolombia_cardless_cashout/domain/model/aggregate.py` — and a private `_transition_status`
method that is the *only* place the status field is assigned:

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
    ...
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

One deliberate difference from bold: bold's `_change_status` raises a single generic
`*UpdateStatusError(current_status, new_status)` for every invalid transition. This standard
keeps §5.5's **one-named-exception-per-invalid-transition** convention instead — the caller
passes its own already-constructed exception in — so the `code` an API consumer sees stays
action-specific (`ORDER_CANNOT_BE_CONFIRMED` vs. `ORDER_CANNOT_BE_CANCELLED`) rather than
one generic `INVALID_STATUS_TRANSITION` for everything. The transitions dict is still the
single source of truth for *which* transitions are legal; only the exception raised on an
illegal one stays per-action.

The dict and `_transition_status` live on the **aggregate that owns the status field**, not
on the shared `AggregateRoot` base — bold doesn't generalize this part either, because the
dict's key/value type and the exception raised are specific to each aggregate's own status
enum. Only `touch()` (identical everywhere) belongs on the base class.

### 5.4 Business rules

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

### 5.5 Domain exceptions

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

`commons.domain.exceptions.DomainError` and its subclasses are defined once — see §13.

### 5.6 Ports

A **port** is an `abc.ABC` in `domain/model/ports.py`, declared by the domain because it
needs a capability the outside world provides (dependency inversion). Exists for exactly two
reasons — full decision tree in §10.2:

1. A synchronous call to a genuinely **external** system (a payment gateway, a tax API).
2. A synchronous call to **another bounded context's internal endpoint**, only to snapshot
   a point-in-time fact this aggregate must own a copy of (never to check
   permissions/existence — the JWT already proves that, §9.3).

### 5.7 Shared value types: `Money`

Ported (trimmed) from `bold.commons.standard_types.money`, which is the strongest example
in any of the three reference codebases of §1.11: every operation a caller could plausibly
need — arithmetic, comparison, formatting, sign checks, splitting a total across rates,
rounding — lives on the value object itself, so no caller anywhere ever reaches into
`.value`/`.currency` to reimplement one of these by hand.

```python
# commons/domain/money.py
import decimal
import enum

from commons.domain import enums, exceptions, value_objects


class Currencies(enums.UpperStrEnum):   # §5.1 — UpperStrEnum, not plain StrEnum: ISO-4217
    COP = enum.auto()                    # codes are uppercase, .value == "COP"
    USD = enum.auto()
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

**Golden-path usage** (§19): `OrderLine.unit_price: money.PositiveMoney` is populated once,
at order-creation time, from the external pricing port already defined above (10.2a) — the
same port that was previously a placeholder gets a concrete purpose here: fetching the
current price for a SKU and letting `Order` snapshot it, for exactly the same reason §9.2
snapshots the customer's profile (a later price change must not rewrite historical orders).
`Order.total` is a **computed `@property`**, never a stored field:

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
for anything fully derived from other fields already on the aggregate (the same `@property`
discipline Google's style guide asks for — "controlling attribute access for... simple
computation," §17.3 — applied to a real, non-trivial case).

---

## 6. Application layer (`services/`)

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
        stock_repo = uow.repo(aggregate.Stock)   # resolved once, reused for get + update —
        # calling uow.repo(aggregate.Stock) twice would return the same memoized instance
        # either way, but one local variable reads as "this function uses one repository."
        stock = stock_repo.get_by_sku(sku)
        stock.reserve(quantity)                  # raises InsufficientStockError → rollback
        stock_repo.update(stock)
```

No `_publish_events()` helper here — `DefaultStockRepository.add`/`.update` drain and record
the entity's events internally, in the same transaction as the write (§7). Rules:

- One function per use case, named as a verb (`create_stock`, `reserve_stock`), not
  `StockService.create`. Group related use-case functions in one module per subcontext
  (`stock.py`); split into more files only once a subcontext genuinely has enough of them.
- **Always** takes `uow` as an explicit parameter — no invisible framework DI inside the
  function. FastAPI's `Depends()` wires it at the entrypoint (§9); the function itself is
  plain, framework-agnostic, testable with a fake UoW.
- **This module is the only place in the whole codebase allowed to call
  `uow.repo(aggregate.Stock)` or `stock.reserve(...)`.** An orchestrator (§10) calls
  `reserve_stock(...)`, never the aggregate directly — see §10.2 for why, verified against
  `bold`'s real orchestrators.
- **`uow.repo(aggregate.Stock)` must be called from inside `with uow.transaction():`, never
  before it opens** — `UnitOfWork.repo` reads `UnitOfWork.session`, which raises
  `RuntimeError` until a transaction is open (§8). A real bug an earlier draft of this
  document had: resolving the repository as the very first statement of the function, one
  line above `with uow.transaction():` instead of one line below it.
- A function using its repository more than once (a `.get` then an `.update`, say) resolves
  it **once** and reuses the local variable, rather than calling `uow.repo(aggregate.X)`
  again for the second call — not a correctness issue (the UoW memoizes the instance either
  way), but two separate-looking calls read as two separate concerns where there's only one.

---

## 7. Adapters — ORM mapping and repositories

Every concrete repository implements one shared contract, declared once in the domain layer
(a repository is a port like any other, §5.6 — the domain declares what it needs, an
adapter provides it):

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

**`add`/`update`, not one unified `put`** — verified against `sona-sso-backend`'s real
`OrganizationRepository` (`uow.organizations.add(org)` on creation,
`uow.organizations.update(org)` on every mutation, two distinct methods, never one). Insert
and update are different operations with different failure modes: an insert on a
`HumanFriendlyId`-keyed aggregate can collide on the primary key and must retry with a fresh
id (§5.2); an update can lose an §8.1 optimistic-concurrency race. An earlier draft of this
document collapsed both into one `session.merge(...)`-based `put`, which can't express the
collision-retry path at all and hides which operation a caller actually means.

`...` marks these as method *stubs* with no body of their own — a contract, not an
implementation (the same convention `BusinessRule`'s abstract methods use, §5.4). This is
different from `pass` on `class Base(DeclarativeBase): pass` a few lines below, or
`class StockId(value_objects.UuidV7Id): pass` (§5.2): those classes are genuinely
*complete* — real, concrete, nothing left to fill in — so `pass` is correct there, not a
placeholder for something still to come. The rule (§17.3): `...` says "implement me
elsewhere"; `pass` says "this is finished, on purpose."

PostgreSQL/SQLAlchemy requires an explicit relational mapping layer that `bold` (DynamoDB,
where the aggregate itself is what's serialized — §0) doesn't need:

```python
# commons/adapters/orm_base.py
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampsMixin:
    """created_at/updated_at in POSIX microseconds (BigInteger) — never `datetime` (§1.8)."""
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
  named exception to §1.9/§17.1, matching Google's own carve-out for `typing`: these
  function as type-annotation syntax, not business logic, and this is exactly what
  `sona-sso-backend`'s real `orm_base.py` does. Everything else from SQLAlchemy is imported
  as the module `sa` and used qualified (`sa.Text`, `sa.select(...)`).
- Bespoke query methods (`get_by_sku`) go directly on the concrete repository class, not the
  generic `Repository[T]` interface — mirrors `bold`'s `custom_repo()` escape hatch (§8).
- `_to_orm`/`_to_entity` are plain module-level functions (`sona-sso-backend`'s convention).
- **Every `add`/`update` ends with `repository_helpers.publish_events(session, entity)`** —
  drains the entity's recorded events and records them to the outbox, in the *same*
  transaction as the write that just happened. This is why `services/*.py` never has a
  hand-called `_publish_events()` helper (§6): a service can no longer forget to call it,
  since the repository does it unconditionally on every write. Verified against bold's own
  documented lifecycle: *"Repository persists atomically: `save(aggregate)` calls
  `uow.publish(event)` inside a transaction"* (`lambdas/CLAUDE.md`) — an earlier draft of
  this document had the service call a `_publish_events()` helper by hand after every
  `.put()` instead, which is exactly the "aggregate records the event, application service
  is responsible for draining it" alternative bold's own convention avoids.
- **`stock.created_at.microseconds` here is not a Law-of-Demeter violation** (§1.11) — this
  pair of functions is the one place in the whole codebase authorized to unwrap a value
  object's internal field, because translating between the domain representation and the
  storage representation is their entire, sole purpose (the Data Mapper pattern, Fowler).
  The same access pattern anywhere in `domain/` or `services/` would be the mistake §1.11
  and §20 call out.

### 7.1 `add` on a `HumanFriendlyId`-keyed aggregate: `insert_with_id_retry`

`Order` (§5.2) is `HumanFriendlyId`-keyed, so its `add` can't just `session.add(...)` and
flush — a genuine, if rare, primary-key collision is possible:

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
`sona-sso-backend`'s real `insert_with_id_retry`, and a genuine bug this document caught in
its own earlier draft: without it, catching the `IntegrityError` and retrying would need a
plain `session.rollback()` to clear the failed statement, but `session.rollback()` rolls back
the *entire* transaction, not just this one insert — discarding every other write already
staged in the same `with uow.transaction():` block (a product-level orchestrator's other
mutations, §10.2), not just the colliding row. `begin_nested()` scopes the rollback to just
this attempt; the outer transaction (and everything else written in it) is untouched.

Only the primary-key constraint triggers a retry — any other `IntegrityError` (a genuine
unique-field violation, e.g. a duplicate order reference) is re-raised immediately, since
regenerating the id would silently create a duplicate under a different key while leaving
the real conflict unaddressed.

---

## 8. Unit of Work

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
from commons.adapters import orm_base, outbox   # orm_base: used by _claim_idempotency_key, §12

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
            yield   # nested call joins the outer transaction — no-op re-entrancy (§10.2)
            return
        self._session = self._session_factory()
        try:
            if idempotency_key is not None:
                self._claim_idempotency_key(idempotency_key)   # §12
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

**Nested transactions are how §10.2's cross-service atomicity actually works**: when a
product-level orchestrator opens `with uow.transaction():` and then calls a subcontext's
service function, which itself opens `with uow.transaction():`, the inner call detects
`self._session is not None` and joins the outer one — one commit, one rollback, for the
whole call chain. This is the mechanism, not an aside.

**Cross-aggregate atomicity policy:**

- **Within the same product**: atomic multi-aggregate transactions are allowed, achieved by
  nested `uow.transaction()` calls across service functions (never by an orchestrator
  calling `uow.repo()` directly — §10.2).
- **Across products**: never share a transaction. Coordination goes through
  `orchestrators/` calling independently-committing service functions (§10.3), or through
  the outbox (§11).

**No I/O inside an open transaction.** A `with uow.transaction():` block holds a checked-out
Postgres connection for its entire duration — a synchronous HTTP call (§10.2a/§10.2b's ports)
made while it's open ties up that connection for the round-trip's full latency, and any
retry/backoff on that call (§10.2a) multiplies it. This was a real bug, found by re-reading
the template's own `confirm_order` against the rule its sibling `create_order` already
followed correctly:

```python
# WRONG — found in an earlier draft of services/orders.py::confirm_order:
with uow.transaction():
    order = uow.repo(aggregate.Order).get(order_id)
    profile = user_profile_port.get_profile(order.customer_id)   # HTTP call — tx still open
    order.confirm(shipping_name=profile.full_name, shipping_email=profile.email)
    uow.repo(aggregate.Order).put(order)
```

The fix has two parts, because a **nested** `uow.transaction()` call joins the outer one as
a no-op (this section, above) — so moving the port call inside `orders.confirm_order`'s own
transaction block doesn't help once that function is called from inside an orchestrator's
already-open outer transaction. The port call has to move to wherever the *outermost*
transaction actually opens:

```python
# RIGHT — services/confirm_order_orchestrator.py:
def confirm_order(*, uow, order_id, user_profile_port: order_ports.UserProfilePort) -> dto.OrderOutputDTO:
    order = orders.get_order(uow=uow, order_id=order_id)          # its own short tx, closes immediately
    profile = user_profile_port.get_profile(...)                  # HTTP call — no transaction open at all

    with uow.transaction():                                       # opens only for the atomic part
        stock.reserve_stock(uow=uow, sku=..., quantity=...)
        return orders.confirm_order(
            uow=uow, order_id=order_id,
            shipping_name=profile.full_name, shipping_email=profile.email,
        )
```

`orders.confirm_order` itself no longer takes a `UserProfilePort` at all — it takes plain
`shipping_name`/`shipping_email` strings. This isn't just a transaction-scope fix, it's a
purity improvement: the single-aggregate service becomes I/O-free business logic once the
snapshot it needs is handed to it, and the port call becomes the orchestrator's problem to
schedule correctly — which is exactly where §10.2 already says cross-cutting composition
belongs. `create_order` needed no equivalent fix because it already fetches its `PricingPort`
result into a plain list *before* `with uow.transaction():` opens (§10.2a) — this rule was
implicit in that one function from the start; `confirm_order` is what exposed that it hadn't
been generalized into a named rule anyone could check the rest of the codebase against.

A plain read with no I/O and no cross-aggregate work (`orders.get_order`) staying wrapped in
its own `with uow.transaction():` is **not** a violation of this rule and is not something to
"optimize away" — verified against `sona-sso-backend`'s own `OrganizationService.get()`,
which wraps a pure read the same way. SQLAlchemy always needs a `Session` to run any query,
read or write (unlike `bold`'s DynamoDB `find_by_id`, which needs no transactional envelope
at all — that difference is infrastructure, not a reason to imitate the DynamoDB shape here).
What actually matters is never letting a *held-open* transaction span a network call.

### 8.1 Optimistic concurrency (race conditions)

The scenario this section exists for: two Lambda invocations both call
`stock_service.reserve_stock(sku=..., quantity=...)` for the same `Stock` at nearly the same
time. Both read `available_quantity=1`. Both decide there's enough. Without a check, both
write, and one write silently overwrites the other — stock gets sold twice. This was a real
gap: an earlier draft of this document defined `AggregateRoot` and the UoW with no answer to
it at all.

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
`AggregateRoot.version` (§5.1) stays a plain `int` — no need for `bold`'s richer
`RootEntityVersion` (`number`/`region`/`date`), which exists specifically to make a
conditional check DynamoDB doesn't provide natively; Postgres already provides it:

```python
# commerce/stock/adapters/orm.py  (excerpt — extends §7's StockOrm)
class StockOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "stock"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(sa.Text, unique=True)
    available_quantity: Mapped[int]
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}
```

`commons.domain.exceptions.ConcurrentModificationError` — a `ConflictError` subclass, §13 —
is what the repository below raises on a lost race:

```python
# commerce/stock/adapters/repository.py  (excerpt — extends §7's DefaultStockRepository)
import sqlalchemy.orm.exc

from commons.domain import exceptions as commons_exceptions


class DefaultStockRepository(repositories.Repository[aggregate.Stock]):
    ...

    def put(self, stock: aggregate.Stock) -> None:
        self._session.merge(_to_orm(stock))
        try:
            self._session.flush()   # forces the version check now, not at commit time
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                f"Stock [{stock.id}] changed concurrently — reload and retry.",
                code="CONCURRENT_MODIFICATION",
            ) from exc
```

`commons_exceptions` is an alias (§17.1) — this file already imports its own subcontext's
`exceptions` module for `StockNotFoundError`; without the alias the two would collide.
`ConcurrentModificationError` is a `ConflictError` subclass, so it needs no new entry in
§13's `_STATUS_FOR` table — the `isinstance` check there already resolves it to HTTP 409.

**What the caller does with it — matching `bold`'s own documented answer, not a blind
retry**: an HTTP entrypoint (§9.1) lets the 409 propagate to the client, which re-fetches
current state and reissues the request — the version field means a stale write fails loudly
instead of silently corrupting data. An event consumer (§9.4) may retry automatically
*only* if re-running the whole handler from a fresh `uow.repo(Stock).get(...)` is safe to
repeat — which it is here, because §12.2's idempotency check already guards the outer
transaction, so a retry after `ConcurrentModificationError` is exactly as safe as SQS's
own at-least-once redelivery already assumes.

**Where this applies:** only on `AggregateRoot` (§5.1), not on every `Entity` — a child
entity inside an aggregate (`OrderLine`, §5.7) has no independent existence to race over;
its consistency is already covered by its owning aggregate root's version.

---

## 9. Entrypoints

### 9.1 Web (`entrypoints/web/{public,internal}.py`)

One Lambda per file, `mangum.Mangum(app)` at the bottom, multiple routes multiplexed through
one FastAPI `app` — the pattern `sona` and `sona-sso-backend` converged on independently:

```python
# commerce/orders/entrypoints/web/public.py   (illustrative — actually lives at product level)
from typing import Annotated

import fastapi
import mangum

from commerce.orders.services import dto, orders

app = fastapi.FastAPI(title="Orders API")


@app.post("/orders", response_model=dto.OrderOutputDTO)
def create_order(
    body: dto.CreateOrderInputDTO,
    user: Annotated["authentication.AuthenticatedUser", fastapi.Depends(require_jwt)],
    uow: Annotated["unit_of_work.UnitOfWork", fastapi.Depends(get_uow)],
) -> dto.OrderOutputDTO:
    return orders.create_order(uow=uow, input_dto=body, created_by=user.id)


handler = mangum.Mangum(app)
```

`typing.Annotated` is imported by name — the same named exception Google's own guide grants
`typing`/`collections.abc` (§17.1); everything else (`fastapi`, `mangum`) is a bare module
import, used qualified (`fastapi.Depends`, `fastapi.FastAPI`), exactly matching
`sona-sso-backend`'s real entrypoint files.

- Routers are **thin**: parse input, call exactly one service function, return its DTO. No
  `domain` import here — enforced by import-linter contract 5 (§16).
- `public.py`: JWT required by default; exempted routes (`/login`, `/register`) say so
  explicitly in the route, not by omission.
- `internal.py`: service-to-service only, different auth dependency
  (`fastapi.Depends(require_service_auth)` — API key or IAM SigV4). Never accepts a customer
  JWT.
- **One file per subcontext, never two subcontexts sharing a router.** `orders` and `stock`
  are independent bounded contexts (§10.4) with independent deploy/scale lifecycles — a
  combined `entrypoints/web/public.py` routing both was an early draft's mistake, caught by
  checking `sona-sso-backend`'s real `entrypoints/web/`: `organizations.py` and
  `sso_connections.py` are two files even though both ship inside the same product, and even
  a Lambda that legitimately *does* compose both contexts (`public.py` there) does so by
  importing each context's already-separate `router`/`*ServiceDep` and overriding their UoW
  binding — never by writing both contexts' routes directly into one file. `orders.py` and
  `stock.py` are the two files here; a future Lambda that needs to expose both together
  composes them the same way `sona-sso-backend`'s `PublicUnitOfWork` does, it doesn't merge
  the route definitions.
- **Every status code is `fastapi.status.HTTP_*`, never a bare int** (`status.HTTP_201_CREATED`,
  not `201`) — §17.1's "import a module, not a name" carve-out for `from fastapi import
  status` already says this; it applies to `status_code=` kwargs and `raise
  fastapi.HTTPException(status_code=...)` alike, verified against every real
  `sona-sso-backend` router file.
- **A port's concrete adapter is constructed here, at the entrypoint — never inside the
  service or orchestrator it's passed into, and never as an `x = param or DefaultAdapter()`
  fallback inside that function.** A private module-level factory (`_get_pricing_port()`)
  builds the adapter and the route handler passes it in as a required keyword argument:

  ```python
  # commerce/entrypoints/web/orders.py
  def _get_pricing_port() -> ports.PricingPort:
      return pricing_adapter.HttpPricingAdapter()

  @app.post("/orders", ..., status_code=status.HTTP_201_CREATED)
  def create_order(body: orders_dto.CreateOrderInputDTO, uow: UowDep, _user: UserDep) -> orders_dto.OrderOutputDTO:
      return orders.create_order(uow=uow, input_dto=body, pricing_port=_get_pricing_port())
  ```

  Verified against bold's real `entrypoints/web/breb/breb_credibanco.py`:
  `_get_breb_cashin_pricing_adapter()` is defined right there in the entrypoint file and
  called at each route's call site; the service/orchestrator functions it feeds all declare
  `breb_cashin_pricing_adapter: ports.BreBCashinPricingAdapter` as a **required** parameter,
  never `| None = None` with a fallback default. The entrypoint is the composition root —
  hiding a `DefaultAdapter()` construction inside a service function via `port or
  DefaultAdapter()` (an anti-pattern this document's own earlier draft had, caught and
  removed) obscures that dependency instead of wiring it explicitly, and it's a different use
  of `x or default` than bold's real one: bold's `self._kyc = kyc_providers or
  kyc_providers_adapter.DefaultKycProvidersAdapter()` sets an instance attribute **once**,
  inside a class's own `__init__`, never inline in a plain function body called on every
  request. This is also why import-linter's entrypoint-thinness contract (§16) has to name an
  exception: an entrypoint importing `orders.adapters.pricing_adapter` to construct it is the
  composition root doing its job, not the entrypoint reaching past the service layer.

### 9.2 Why `internal.py` exists, and what it's for

Not a general cross-context escape hatch. Exists for exactly one reason (§5.6, §10.2b):
another bounded context needs a point-in-time snapshot of data it must own a copy of.
Golden-path example: `commerce/orders` confirming an order snapshots the customer's
name/email/address via `GET /internal/users/{id}/profile`, so a later profile change doesn't
retroactively rewrite historical orders. It is explicitly **not** used to check "does this
user exist / are they active" — the JWT already proves that (§9.3).

### 9.3 Authentication

RS256 JWT, asymmetric. Only `identity/users` holds the private key and signs; the public key
is distributed so any product verifies **locally, with no network call** — what makes §9.2's
"no synchronous existence check" rule viable at all.

- **Access token**: ~15 minutes TTL, validated locally on every request.
- **Refresh token**: long-lived, opaque, stored in `identity/users/adapters/orm.py`
  (Postgres — no second data store, §0), revocable. Revoking it is how a deactivated user's
  session actually dies quickly, with no product ever calling back to `users`.
- `identity/entrypoints/cron/expire_refresh_tokens.py` sweeps expired rows on a schedule —
  §18.

### 9.4 Events (`entrypoints/events/`)

One handler file per (source topic, consuming product) pair — `sona`'s proven granularity.
The dispatch *mechanics* underneath, though, follow `bold`, not `sona` — `bold`'s
`entrypoints/events/*` handlers receive already-typed events and dispatch by
**`type(event)`** through a strategy map (`lambdas/CLAUDE.md`: *"Use a strategy map inside
`EventHandler` (`type(event) → ProcessHandler`) to dispatch"*), never by a hand-maintained
string. `sona`'s real `BaseSQSEventHandler.process_sqs_event` needs **two** dictionaries
kept in sync by hand — `event_map: dict[str, type[Event]]` for parsing and
`event_handlers: dict[type[Event], Callable]` for dispatch — and `sona`'s own operational
notes list exactly the failure this invites: *"unmapped event names in `_EVENT_MAP`"* as a
recurring incident. This standard closes that gap by making the event class itself the only
source of truth for its wire name (`DomainEvent.event_type`, §11.1, a *computed* field —
it cannot drift from the class because it *is* the class name), so there is exactly **one**
registration list, not two dictionaries to keep aligned.

It goes one step further than either reference: `bold`'s own handlers (see
`_confirm_or_revert_breb_cashin` in `breb/breb_cashin/entrypoints/events/
breb_cashin_confirmation.py`) still make every handler function individually responsible for
opening `with uow.transaction(idempotence_key=...)` and catching `DuplicatedTransactionError`
— easy to forget on a new handler, exactly the kind of per-file boilerplate §1.6 already
flags as a real, sourced risk (`sona-sso-backend` shipped the equivalent omission for
`pull_events`, not for this, but the *shape* of the mistake — a rule that depends on every
author remembering it — is identical). For the common case — a handler with no I/O before
its one write — the dispatcher does the wrapping itself, so there is nothing to forget:

```python
# commons/adapters/sqs.py
import dataclasses
from typing import Any, Callable

from commons.adapters import logs, unit_of_work
from commons.domain import events

_LOGGER = logs.get_logger()


@dataclasses.dataclass(frozen=True)
class EventConsumer[EventT: events.DomainEvent]:
    """One registered (event type, handler) pair — the single place that names both.

    A plain `dataclass`, not a `ValueObject`/Pydantic model — see §17.3 for why: this holds
    a `type` and a `Callable`, constructed once in Python code at import time, never parsed
    from JSON or any other external input. Pydantic validation exists to police a boundary
    with the outside world; there is no such boundary here to police.

    Exactly one of `handle`/`handle_without_uow` must be set — enforced in `__post_init__`,
    not just by convention. Two separate, non-union fields, **not**
    `handle: Callable[[UoW, EventT], None] | Callable[[EventT], None]` dispatched by
    inspecting `len(inspect.signature(consumer.handle).parameters)` at runtime, which an
    earlier draft of this document did: mypy cannot narrow a union of different-arity
    callables from a runtime arity check, so that version needed a `# type: ignore` at every
    call site that actually invoked `consumer.handle`. Two mutually-exclusive fields need
    none — each is one concrete, non-union callable type — and the registration call site
    states its intent directly (`handle=` vs `handle_without_uow=`, below) instead of the
    dispatcher inferring it from how many parameters a function happens to declare.
    """
    event_class: type[EventT]
    handle: Callable[[unit_of_work.UnitOfWork, EventT], None] | None = None
    handle_without_uow: Callable[[EventT], None] | None = None

    def __post_init__(self) -> None:
        if (self.handle is None) == (self.handle_without_uow is None):
            raise ValueError(
                "EventConsumer needs exactly one of handle/handle_without_uow, not both/neither."
            )


def process_sqs_event(
    *,
    event: dict[str, Any],
    consumers: list[EventConsumer],
    consumer_name: str,
    uow_factory: Callable[[], unit_of_work.UnitOfWork],
) -> None:
    by_type_name = {c.event_class.__name__: c for c in consumers}
    _LOGGER.info("%s - event received", consumer_name)

    for record in event.get("Records", []):
        body = record.get("body")
        if not body:
            _LOGGER.warning("Empty SQS message body")
            continue

        envelope = events.parse_envelope(body)   # json.loads + shape check, no event class yet
        consumer = by_type_name.get(envelope.get("event_type"))
        if consumer is None:
            _LOGGER.warning("Unknown event type: %s", envelope.get("event_type"))
            continue

        parsed_event = consumer.event_class.model_validate(envelope)
        try:
            if consumer.handle is not None:
                uow = uow_factory()
                with uow.transaction(idempotency_key=parsed_event.idempotence_key()):
                    consumer.handle(uow, parsed_event)
            else:
                assert consumer.handle_without_uow is not None  # __post_init__ guarantees it
                consumer.handle_without_uow(parsed_event)
        except unit_of_work.DuplicatedTransactionError:
            _LOGGER.info("%s already processed, skipping", parsed_event.idempotence_key())
        except Exception:
            _LOGGER.exception("Error handling %s", envelope.get("event_type"))
            raise   # let SQS/Lambda's own retry + DLQ redrive take over — no local retry
```

Each product's event entrypoint is then one list, one call:

```python
# commerce/orders/entrypoints/events/on_user_deactivated.py   (illustrative path)
from typing import Any

from commons.adapters import logs, sqs, unit_of_work

from identity.users.domain.model import events as user_events
from commerce.orders.services import orders

_LOGGER = logs.get_logger()


def _handle_user_deactivated(uow: unit_of_work.UnitOfWork,
                              deactivated: user_events.UserDeactivated) -> None:
    orders.cancel_pending_orders_for_user(uow=uow, user_id=deactivated.user_id)


_CONSUMERS = [
    sqs.EventConsumer(event_class=user_events.UserDeactivated, handle=_handle_user_deactivated),
]


def handler(event: dict[str, Any], context: Any) -> None:
    sqs.process_sqs_event(event=event, consumers=_CONSUMERS,
                           consumer_name="orders-on-user-deactivated",
                           uow_factory=unit_of_work.build)
```

`_handle_user_deactivated` receives a `uow` **already inside an idempotency-guarded
transaction** and calls exactly one function in the subcontext's own `services/` module
(never `domain/` directly, §4) — there is no `with uow.transaction(...):` for it to remember
or forget. `DuplicatedTransactionError` never reaches it; the dispatcher already turned a
duplicate delivery into a log line and a clean return, not an error.

**The escape hatch, for `bold`'s real harder case.** Some handlers genuinely need I/O
*before* they know what to write — `bold`'s `_confirm_or_reject_breb_cashin` calls an
external provider (`await breb_adapter.get_transaction_status(...)`) first, and only then
decides which of two different write paths to take. Holding a database transaction open
across that external call would be its own anti-pattern (a long-held transaction blocking a
connection on network I/O). For that case, register with `handle_without_uow: Callable[[EventT],
None]` instead of `handle` — the dispatcher branches on which field is set and does **not**
auto-wrap `handle_without_uow`; the handler does its external call first, then opens
`with uow.transaction(idempotency_key=event.idempotence_key()):` itself around just the
write, exactly as `bold` does today. This is the one place this standard asks an author to
remember the wrapping by hand — narrowly scoped to "I need I/O before I can write," not the
default.

One thing neither `bold` nor `sona` implements, worth adding at the CDK/infra level on top
of this handler shape: **SQS partial-batch-failure reporting**
(`FunctionResponseTypes: [ReportBatchItemFailures]` on the event source mapping, the handler
returning `{"batchItemFailures": [{"itemIdentifier": ...}]}` for just the records that
failed). Without it, a re-raise on any single bad record causes the *whole* batch to be
redelivered — safe here because every handler is idempotent (§12.2), but wasteful. Worth
doing once idempotency is in place; not required to get this pattern correct on day one.

### 9.5 Cron (`entrypoints/cron/`)

EventBridge-scheduled. Housekeeping only — see §18 for the one load-bearing exception.

---

## 10. Orchestration

Three tiers. Walk this decision tree in order for every new use case:

```
Does the use case mutate exactly one aggregate instance?
├── YES → §10.1: call the SUBCONTEXT'S OWN services/ function directly. No orchestrator.
└── NO → does it need a fact from outside this bounded context?
    ├── YES, synchronously, from an EXTERNAL system → §10.2a: domain port + adapter.
    ├── YES, synchronously, from ANOTHER BOUNDED CONTEXT → §10.2b: internal HTTP port,
    │   used ONLY to snapshot owned data (§9.2).
    └── does it mutate multiple aggregates?
        ├── Same product → §10.2: product-level orchestrator, calling SERVICES functions,
        │   composed into ONE atomic transaction via nested uow.transaction() (§8).
        └── Different products → §10.3: top-level orchestrator OR async event reaction
            (§11) — consistency is eventual, no shared transaction, ever.
```

### 10.1 Single aggregate — no orchestrator

Call the subcontext's own service function (§6) from the entrypoint directly.

### 10.2 Same product, multiple aggregates — product-level orchestrator

**The orchestrator calls other subcontexts' `services/` functions. It never calls
`uow.repo(...)` or an aggregate method itself.** This is not a style choice — it is exactly
how `bold`'s real orchestrators are written, verified directly against
`apply_and_confirm_or_reject_breb_cashin_orchestrator.py`: it imports
`breb_cashin_management` (the service module) and calls
`apply_and_confirm_breb_cashin_orchestrator.apply_and_confirm_breb_cashin(...)` /
`reject_breb_cashin_orchestrator.reject_breb_cashin(...)` — never touches `uow.repo(...)` or
an aggregate directly itself. `bold`'s own `CLAUDE.md` states the layer order explicitly:
`entrypoints → services → domain.model`; an orchestrator is a `services/` module, and it
respects that same order with respect to every OTHER subcontext it coordinates.

```python
# commerce/services/confirm_order_orchestrator.py
from commons.adapters import logs, unit_of_work

from commerce.orders.domain.model import ports as order_ports
from commerce.orders.domain.model import value_objects as order_value_objects
# ^ typing only — the contract-6 exception (§16) now covers value_objects AND ports: a
#   value object for a plain pass-through param, a port ABC for a caller-supplied adapter
#   this function never constructs itself — never aggregate/events/rules/adapters.
from commerce.orders.services import dto, orders
from commerce.stock.services import stock

_LOGGER = logs.get_logger()


def confirm_order(
    *, uow: unit_of_work.UnitOfWork, order_id: order_value_objects.OrderId,
    user_profile_port: order_ports.UserProfilePort,
) -> dto.OrderOutputDTO:
    # The profile fetch happens BEFORE with uow.transaction() opens — §8's no-I/O-inside-an-
    # open-transaction rule. A nested uow.transaction() call joins the outer one as a no-op
    # (§8), so calling the port from inside orders.confirm_order itself wouldn't help: THIS
    # function's own transaction is what actually holds the connection open.
    order = orders.get_order(uow=uow, order_id=order_id)
    profile = user_profile_port.get_profile(
        order_value_objects.CustomerId(value=uuid.UUID(order.customer_id))
    )

    with uow.transaction():
        for line in order.lines:
            stock.reserve_stock(uow=uow, sku=line.sku, quantity=line.quantity)
        return orders.confirm_order(
            uow=uow, order_id=order_id,
            shipping_name=profile.full_name, shipping_email=profile.email,
        )
```

`orders.get_order`, `stock.reserve_stock`, and `orders.confirm_order` are ordinary
application-service functions (§6), each opening its **own** `with uow.transaction():`
internally — which, once inside the outer `with uow.transaction():` above, simply joins it
(§8). If `stock.reserve_stock` raises `InsufficientStockError` for any line, the whole
mutation rolls back atomically: `Order` is never left half-confirmed, no `Stock` is left
partially decremented. The orchestrator never sees `Stock` or `Order` as domain objects at
all — only their services' DTOs and exceptions. `orders.confirm_order` itself takes plain
`shipping_name`/`shipping_email`, not the port — see §8's worked example of why the fetch
had to move up to here instead of staying inside that function's own transaction block.
`user_profile_port` is never constructed here either — the entrypoint (§9.1) builds the
concrete adapter and passes it in; this function only knows the port's abstract shape.

**(10.2a) External synchronous port** — the golden path's concrete case: `Order` needing the
current price for a SKU to snapshot onto each `OrderLine` (§5.7). Defined in
`orders/domain/model/ports.py` as `PricingPort`, implemented in
`orders/adapters/pricing_adapter.py`, injected into the application service as a **required**
keyword argument (never `port: PricingPort | None = None` with an `or DefaultAdapter()`
fallback — §9.1 explains why that DI decision belongs to the entrypoint, not the service) —
never called from the aggregate itself (§5.3). Modeled on `bold`'s `BreBCashinPricingAdapter`,
which plays the identical role: an external price lookup, called from application code, with
the result handed to the aggregate as a plain parameter.

The adapter itself: retries transient failures with `backoff.on_exception` and parses the
response into a typed Pydantic DTO before it ever touches domain code — both verified
against bold's real `bancolombia_cardless_cashout/adapter.py`:

```python
# commerce/orders/adapters/pricing_adapter.py
import backoff

_RETRYABLE_ERRORS = (httpx.ConnectTimeout, httpx.ReadTimeout)


class _PriceResponseDTO(pydantic.BaseModel):
    currency: str
    unit_price: decimal.Decimal


class HttpPricingAdapter(ports.PricingPort):
    @backoff.on_exception(backoff.expo, _RETRYABLE_ERRORS, jitter=backoff.full_jitter, max_tries=3)
    def get_unit_price(self, sku: commerce_value_objects.Sku) -> money.PositiveMoney:
        response = self._client.get(f"{self._base_url}/prices/{sku.value}")
        response.raise_for_status()
        payload = _PriceResponseDTO.model_validate(response.json())
        return money.PositiveMoney(currency=money.Currencies(payload.currency), value=payload.unit_price)
```

Parsing into `_PriceResponseDTO` first, rather than indexing `response.json()` by key
directly, is the same split bold's own adapter makes via its `mappers.map_response_to_...`
functions: a malformed or renamed upstream field fails loudly with a `pydantic.ValidationError`
naming the exact field, instead of a bare `KeyError` with no context. `max_tries=3` with
`backoff.expo`/`jitter=backoff.full_jitter` is bold's exact real configuration on every HTTP
adapter method that calls an external system — copied verbatim, not invented; only the
retried exception types are chosen per adapter (`httpx.ConnectTimeout`/`httpx.ReadTimeout`
here — the transient network failures worth retrying, never a 4xx/5xx business response,
which `response.raise_for_status()` turns into a non-retryable exception instead).

**(10.2b) Internal synchronous port** — see §9.2. Same shape (required kwarg, `backoff`,
typed response DTO), but the adapter calls another product's `entrypoints/web/internal.py`
over HTTP instead of a third party, and — because the golden path's only caller is a
product-level orchestrator, not a single-aggregate service — it's the **orchestrator**,
not `orders.confirm_order`, that receives `UserProfilePort` and calls it, and it must do so
before opening its own transaction (§8's worked example).

### 10.3 Cross-product — top-level orchestrator, eventual consistency

**This tier needs a genuine reason two products' services must be called synchronously in
one request, each committing independently** — not merely "this use case happens to touch
two products." Most cross-product relationships are better served by §9.4's event
consumer (§11's outbox, eventual consistency) than by a synchronous orchestrator: reach for
`orchestrators/` only when the caller genuinely needs *both* results back in the same
response, and an async reaction (below) is unacceptable UX, not just less convenient to
write.

**This golden path's own cross-product relationship is the counter-example, not an
instance of this tier — worth walking through because getting this wrong once already
shaped this document.** A deactivated `identity.users.User` should stop that customer's
pending `commerce.orders.Order`s. An earlier draft of this template had
`orchestrators/deactivate_user_cascade.py`: one function, unconditionally forwarding to
`auth.deactivate_user`, with a comment explaining that `commerce` reacts *asynchronously*
via the event and that a second, synchronous call must never be added. Read literally, that
function was never doing cross-product orchestration at all — the entire "cascade" happens
outside it, via §9.4's event consumer, and it forwarded to exactly one service function
unconditionally: precisely the **Middle Man** §22.2 already names and says to delete. It
took someone asking "why is this an orchestrator if it only calls one aggregate?" to notice
the flagship example for this section was violating this document's own rule. Fixed: the
function is gone, `entrypoints/web/public.py`'s `deactivate_me` route calls
`auth.deactivate_user` directly (§10.1 — it's a single-aggregate use case, full stop), and
the comment explaining why commerce's reaction is event-driven, not a second call, now lives
on `auth.deactivate_user` itself, where a future maintainer tempted to add that second call
will actually read it.

**The shape a *genuine* tier-3 orchestrator takes**, for when a real case arises — receives
**already-constructed application-service modules or UoWs**, never a raw `Session`, never a
FastAPI object, staying framework-agnostic and testable with plain mocks
(`sona-sso-backend`'s pattern, adopted as-is):

```python
# orchestrators/<something>.py — illustrative shape, not a real file in this template;
# this golden path's own cross-product relationship didn't turn out to need this tier (above)
def some_cross_product_flow(*, product_a_uow, product_b_uow, ...) -> ResultDTO:
    result_a = product_a_service.do_thing(uow=product_a_uow, ...)   # commits independently
    result_b = product_b_service.do_other_thing(uow=product_b_uow, ...)  # commits independently
    return ResultDTO.from_both(result_a, result_b)
```

Two separate transactions, never one shared across products (that couples the availability
of two independently-deployable systems to one database transaction — the actual
anti-pattern this standard avoids, contrast with §10.2, which stays inside one deployable
unit and one database). **No compensation/saga machinery** — if step 2 must be guaranteed
even when the caller doesn't wait for a response, that guarantee comes from the outbox +
idempotent consumer (§11/§12), not a retry loop written into the orchestrator.

### 10.4 A deliberate divergence from the book: Order + Stock

Cosmic Python chapter 7 resolves the structurally identical `Batch`/`Product` problem by
**merging `Batch` into the `Product` aggregate**, because a `Batch`'s only reason to change
is allocation to an order line — it has no independent lifecycle.

This standard's golden path keeps `Order` and `Stock` **separate**, coordinated by §10.2's
orchestrator. Deliberate, and for a reason beyond pedagogy: **`Stock` has an independent
lifecycle `Batch` does not** — supplier restock, manual adjustment, damage write-off, none
involving any `Order`. That asymmetry is the DDD signal for separate aggregates. If your own
"stock" concept genuinely has no life outside order allocation, follow the book and merge
it — don't cargo-cult this repo's separation.

Practical rule: **default to merging** two things that always change together; **only**
separate them, coordinated by an orchestrator, when at least one has a real independent
reason to change.

---

## 11. Domain events and the Outbox pattern

### 11.1 Event hierarchy

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

        Never hand-maintain a parallel string constant for this (e.g. a `"USER_DEACTIVATED"`
        literal declared separately from the class) — that duplication is exactly what let
        `sona`'s own event map drift from its event classes in practice (its own
        troubleshooting notes list "unmapped event names" as a recurring failure). A
        computed field can't drift from the class name, because it *is* the class name.
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

### 11.2 Why Outbox is mandatory, not optional

- `sona` (DynamoDB) gets atomicity **for free** — `uow.publish()` writes the event inside
  the same `transact_write_items` call as the aggregate write.
- `sona-sso-backend` (Postgres) records events and **never publishes them** — the drain
  point was never built (§0, §20).
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
    created_at: Mapped[int] = mapped_column(sa.BigInteger)   # PosixTime microseconds, §1.8
    published_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
```

- `uow.outbox.record(event)` (§6, §8) inserts a row **inside the same
  `with uow.transaction():`** as the aggregate write — the Postgres-native equivalent of
  what DynamoDB gives `bold` automatically.
- A separate **relay** (`cron`-triggered, polling every 10–30s — `bold`'s `EventsClient`
  interval) reads unpublished rows, publishes each to SNS/EventBridge, sets `published_at`.
  Only `IntegrationEvent` rows leave the process.
- Fan-out follows `sona`'s proven shape (§0): SNS topic per product, filtered SQS queue per
  consumer, one Lambda per queue, DLQ + `maxReceiveCount` on every queue.

### 11.3 What NOT to build

No in-process message bus, no `Command` dataclasses, no `messagebus.handle()` dispatch table
(§1.10). The outbox relay and event-consumer Lambda entrypoints are the only "bus" here.

---

## 12. Idempotency

Two mechanisms, one underlying trick: claim a key inside the same transaction as the
effect, let a unique constraint deduplicate.

### 12.1 HTTP mutations — `Idempotency-Key` header

```python
# commons/adapters/orm_base.py  (continued)
class IdempotencyKeyOrm(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    created_at: Mapped[int] = mapped_column(sa.BigInteger)   # PosixTime microseconds, §1.8
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
`DUPLICATED_TRANSACTION` (§13). Scope to **creation** endpoints only —
`suspend`/`resume`/`delete` are already naturally idempotent at the domain level.

### 12.2 Event consumers — event-derived idempotency key

No second table — `IdempotencyKeyOrm` (§12.1) is reused as-is. `UnitOfWork.transaction
(idempotency_key=...)` is one generic mechanism with two call sites, not two mechanisms:

Same mechanism as §12.1, fed `event.idempotence_key()` (§11.1) instead of a client header —
directly answering "can we just do what `bold` does with `idempotence_key`": yes, and it's
the same Postgres primitive, not a separate system. A duplicate SQS delivery hits the unique
constraint, the transaction rolls back cleanly, the handler catches
`DuplicatedTransactionError` and returns — acknowledged, not retried, not double-applied.

---

## 13. Error handling and exception hierarchy

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
class ConcurrentModificationError(ConflictError): pass   # a write lost a race — see §8.1
```

Each of these is `pass`, not `...` — every one is a complete, immediately instantiable
class (`raise NotFoundError("...")` works today, nothing left to fill in), the same category
as `StockId(UuidV7Id): pass` (§5.2) or `Base(DeclarativeBase): pass` (§7), not the
abstract-method category `Repository[T]` (§7) uses `...` for. An earlier pass over this
document used `...` here — inconsistent with its own rule (§17.3) once actually checked
against it, fixed here.

Ported from `sona-sso-backend` over `bold`'s `CustomException(status_code, code,
exception_type)`, because the `retriable` flag is directly useful for event-consumer retry
logic (§9.4) in a way a raw HTTP status code isn't. Every subcontext's `exceptions.py`
subclasses one of these:

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

This is the **only** place HTTP status codes get decided.

---

## 14. Shared kernel (`commons/`)

Import-linter (§16) enforces: `commons` never imports from any product. See §3.2 for the
product-local `commons/` tier that sits above this. Contents (already shown inline in §5–13,
summarized here):

```
commons/
├── domain/{base_model,entities,aggregates,value_objects,enums,money,events,business_rules,
│           exceptions,repositories,audit}.py  # money.py: Money — see §5.7;
│                                              # enums.py: UpperStrEnum — see §17.3;
│                                              # audit.py: AuditEntry — see §14.2
├── application/dto.py
└── adapters/
    ├── settings.py           # Settings(pydantic_settings.BaseSettings), get_settings() —
    │                        # see §14.1; every env var this codebase reads, one vocabulary
    ├── engine.py            # sync session factory, NullPool outside local dev
    ├── orm_base.py           # Base, TimestampsMixin, IdempotencyKeyOrm (shared by both
    │                        # §12.1 and §12.2), OutboxEventOrm, AuditLogOrm — see §14.2
    ├── unit_of_work.py        # UnitOfWork, register_repo (§8); uow.audit — see §14.2
    ├── repository_helpers.py   # insert_with_id_retry (§5.2/§7.1), publish_events (§7)
    ├── outbox.py               # OutboxRepository (§11.2)
    ├── audit.py                # AuditRepository — see §14.2
    ├── outbox_relay.py          # publish_pending() — reads the outbox, calls SNS (§11.2)
    ├── sqs.py                    # EventConsumer, process_sqs_event() (§9.4)
    ├── authentication.py          # RS256 jwt_validator + issuer (§9.3)
    ├── logs.py                    # get_logger() — see §17.2
    └── api/
        ├── exception_handler.py  # status_for() (§13)
        └── middleware.py          # request logging
```

**Exactly one global shared layer.** `sona`'s three coexisting generations
(`shared_package`→`sona_common`→`common`) is the failure mode this rule prevents (§20):
extend `commons/`, never fork it.

### 14.1 Configuration: one settings vocabulary — split between shared and local

The same "one vocabulary" principle §13 applies to exceptions, applied to configuration:
**every environment variable this codebase reads goes through a `Settings` field, never a
scattered `os.environ[...]` call in whatever adapter happens to need it.** `pydantic-settings`
was already a declared dependency (`pyproject.toml`) — an earlier draft of this document's
own template never actually used it, hand-rolling weaker `os.environ.get(...)` reads instead,
with `PRICING_SERVICE_BASE_URL`/`IDENTITY_INTERNAL_API_BASE_URL`/`INTERNAL_API_KEY` read
directly in whichever adapter or entrypoint needed them — `INTERNAL_API_KEY` duplicated
across two unrelated files with nothing declaring it required in one place.

"One vocabulary" does **not** mean one class. The shared `commons.adapters.settings.Settings`
holds only what's genuinely cross-cutting — used by `commons/` itself, or by more than one
product:

```python
# commons/adapters/settings.py
import enum

import pydantic_settings


class Environment(enum.StrEnum):
    LOCAL = enum.auto()
    TEST = enum.auto()
    DEV = enum.auto()
    STAGING = enum.auto()
    PROD = enum.auto()


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Environment = Environment.LOCAL
    db_host: str = "localhost"
    db_port: int = 5432   # a malformed DB_PORT fails at Settings() construction, not on
                           # the first query that happens to touch it
    jwt_private_key_pem: str    # required, no default — a misconfigured Lambda that can
    jwt_public_key_pem: str     # issue or verify forgeable tokens is a security incident,
                                 # not a place for a silently-wrong fallback
    internal_api_key: str       # two consumers (identity's own auth dependency AND
                                 # commerce's user_profile_adapter) — a real cross-product
                                 # concern, not a product-local one

    @property
    def postgres_uri(self) -> str:
        return f"postgresql+psycopg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()
    return _SETTINGS
```

Anything with exactly **one** consumer does not go on this class — it's a local
`_Settings(settings.Settings)` subclass declared right in the file that needs it, a
module-level `_SETTINGS = _Settings()` singleton next to it. This is bold's own real
convention, used well over a thousand times across its codebase (`class _Settings
(commons_settings.Settings)`, e.g. `accounting/loans/revolving/adapters
/biometric_identity_provider.py`) and stated directly in its own `CLAUDE.md`: "Settings:
module-level `_Settings(commons_settings.Settings)` singleton `_SETTINGS`; config from env
vars or SSM." This template needs no SSM (that part is genuinely bold's heavier,
scale-appropriate machinery this golden path doesn't need — the `sona-sso-backend`
precedent this section was originally verified against) — but the *local-subclass* half of
bold's pattern isn't about SSM at all, and this template follows it exactly:

```python
# commerce/orders/adapters/pricing_adapter.py
class _Settings(settings.Settings):
    pricing_service_base_url: str   # this adapter's only consumer


_SETTINGS = _Settings()


class HttpPricingAdapter(ports.PricingPort):
    def __init__(self, *, base_url: str | None = None, ...) -> None:
        self._base_url = base_url or _SETTINGS.pricing_service_base_url
        ...
```

This isn't naming hygiene, it's a real correctness fix an earlier draft of this template got
wrong: putting `pricing_service_base_url` and `identity_internal_api_base_url` directly on
the shared `Settings` class meant **every** Lambda in this system had to have
`PRICING_SERVICE_BASE_URL` set in its own environment just for `Settings()` to construct —
including identity's, which never touches pricing at all (every entrypoint calls
`unit_of_work.build()`, which reads this same class; a required field with one real consumer
coupled every unrelated Lambda's boot to it). Verified directly: with `pricing_service_base_url`
still on the shared class, `identity/entrypoints/web/internal.py` fails to import without
`PRICING_SERVICE_BASE_URL` set; with it moved to `pricing_adapter.py`'s own `_Settings`,
identity's entrypoints import cleanly without it, and `commerce/entrypoints/web/orders.py`
(which does import `pricing_adapter`) still fails loud, immediately, if it's missing — the
failure now belongs to the one Lambda that actually needs the value, not every Lambda in the
system.

`commons.adapters.outbox_relay.py`'s two callers (`commerce/entrypoints/cron/outbox_relay.py`,
`identity/entrypoints/cron/outbox_relay.py`) follow the same split: each has its own
`_Settings` with just its own `sns_topic_arn_<product>` field — not a shared
`sns_topic_arn(product: str)` dispatch method on the global class that has to know both
product names by string.

The one deliberate exception to "every env var goes through a `Settings` field" is
`commons.adapters.logs.py`'s `os.environ.get("AWS_LAMBDA_FUNCTION_NAME", ...)` — verified
against bold's identical `commons/cloud/logs.py`, which reads the same platform-injected
variable the same direct way. `AWS_LAMBDA_FUNCTION_NAME` is set by the Lambda runtime itself,
not application configuration a team chooses — it was never a candidate for `Settings` in
either codebase.

`get_settings()` is a **cached module-level singleton**, the same shape
`commons.adapters.engine`'s own `_engine`/`_session_factory` module-level caching already
uses — construct once per cold start, not once per call.

### 14.2 Audit log: who did what, without a growing central file

An append-only record of who did what, shared by every product — not a subcontext-owned
aggregate, because every product needs to write to the same log. Verified against two real
precedents that agree on placement, disagree on shape:

- `bold`: `AuditLog(ValueObject)` embedded in `AuditableEvent(DomainEvent)`
  (`commons/base_types.py:740-781`) — the audit stamp rides the existing event pipeline,
  tagged for separate GSI indexing (`commons/events/commons.py:319-345`). Weak identity
  guarantees: `author` is optional free text (`request.user_id`, an email, `"Merchant:
  {client_id}"`, or `None`), no before/after diff.
- `sona-sso-backend`: a dedicated `audit` bounded context — Postgres table, port/adapter,
  same-transaction write, explicit before/after `changes` diff. Stronger, but built for a
  single-tenant-anchor domain (every bounded context there revolves around `org_id`) — its
  `AuditRepository.list_for_org` is the *only* query, so entries written with no org (its own
  `console_auth` login/logout rows) are permanently unreachable through the API, findable
  only by direct DB access.

This standard keeps `bold`'s **placement** (a shared vocabulary in `commons/`, no dedicated
bounded context, no `services/` layer of its own — mirrors `OutboxRepository`, which is also
a concrete class directly in `commons/adapters/`, not an ABC a domain test fakes) and
`sona-sso-backend`'s **shape** (a real Postgres table, a repository, same-transaction write,
a `changes` diff) — while fixing the query gap by keying lookups on the entity, not a
tenancy anchor this standard's multi-product domain doesn't have:

```python
# commons/domain/audit.py
class Actor(value_objects.ValueObject):
    """`id` is a plain `str`, not a typed value object — `HumanFriendlyId` doesn't validate
    format, so wrapping it bought no real guarantee, and the actor isn't always a `User`
    anyway (a call authenticated by `INTERNAL_API_KEY`, §9.2, has no `UserId` at all). `id`
    is `None` for system-initiated entries (a cron job); `label` is always set — a
    human-readable snapshot taken at write time, so the entry stays legible even after the
    referenced user is later deleted or renamed."""

    id: str | None
    label: str


class AuditEntry(value_objects.ValueObject):
    id: int | None = None
    actor: Actor
    action: str
    aggregate_type: str
    aggregate_id: str
    changes: dict[str, Any] = pydantic.Field(default_factory=dict)
    created_at: value_objects.PosixTime = pydantic.Field(default_factory=value_objects.PosixTime.now)
```

`Actor` is its own value object, not two loose `actor_id`/`actor_label` parameters threaded
through every service function signature: it comes from exactly one place — the verified
JWT (or `INTERNAL_API_KEY`) at the entrypoint's composition root — never from a request-body
DTO (`CreateOrderInputDTO` and friends carry only what the *client* sent; trusting a
client-supplied actor id would let any caller claim to be anyone). An entrypoint builds one
`Actor` and threads it down through the orchestrator/service call, the same way it already
threads a `PricingPort`/`UserProfilePort` instance rather than passing its constructor
arguments separately (§10.2a/b).

`aggregate_type`/`aggregate_id` — and `action` — are plain `str`, not typed value objects:
`commons/` cannot import any product's domain (contract 4), and no single Postgres FK can
point at `orders`, `stock`, and `users` simultaneously — nor would a real FK be correct here
even if it could: deleting the referenced row must never delete or orphan its own audit
trail (`ON DELETE CASCADE` erases the evidence exactly when it's needed; `ON DELETE SET
NULL`, what `sona-sso-backend` does, is what produces its own orphaned-entries gap). Named
`aggregate_type`/`aggregate_id`, not `entity_type`/`entity_id`: this codebase already
distinguishes `Entity[IdT]` from `AggregateRoot[IdT]` (`commons/domain/entities.py` vs
`aggregates.py`), and every audit-writing call site sits right where `uow.repo(...).add`/
`.update` does — always the aggregate root being persisted, never a child entity inside it.

**This is the actual answer to "won't the list of actions/aggregates just keep growing in
one file as the app grows?"** — verified directly against `sona-sso-backend`'s real code: it
doesn't, because `action` is never a shared enum. Each bounded context declares its own
local `AuditAction`/`AuditAggregateType` enum (`OrgAuditAction`, `SsoConnectionAuditAction`,
`ConsoleAuditAction`, one per context, each in that context's own `domain/model/`) and passes
`.value` in — `commons/` never imports any of them, never grows when a new product does:

```python
# identity/users/domain/model/value_objects.py
class AuditAggregateType(enum.StrEnum):
    USER = enum.auto()


class AuditAction(enum.StrEnum):
    REGISTERED = enum.auto()
    DEACTIVATED = enum.auto()
```

```python
# commerce/entrypoints/web/orders.py — the composition root builds the Actor once, from
# the verified JWT, and threads it all the way down (§9.1/§10.2)
@app.post("/orders", ...)
def create_order(body: orders_dto.CreateOrderInputDTO, uow: UowDep, user: UserDep):
    return orders.create_order(
        uow=uow, input_dto=body, pricing_port=_get_pricing_port(),
        actor=audit.Actor(id=user.user_id, label=user.user_id),
    )
```

```python
# identity/users/services/auth.py — inside the same `with uow.transaction():` as the
# aggregate write, same pattern as `uow.outbox.record(...)`
uow.repo(aggregate.User).add(user)
uow.audit.add(
    audit.AuditEntry(
        actor=audit.Actor(id=None, label="self-registration"),  # no authenticated actor yet
        action=value_objects.AuditAction.REGISTERED,
        aggregate_type=value_objects.AuditAggregateType.USER,
        aggregate_id=user.id.value,
    )
)
```

A system-initiated entry (a cron job, an async event reaction) builds its own `Actor` with
`id=None` and a `"system:<what triggered it>"` label — `commerce/orders/services/orders.py`'s
`expire_abandoned_orders` (cron) and `cancel_pending_orders_for_customer` (the async
reaction to `UserDeactivated`, §9.4/§10.3) both do this; the latter still sets `actor.id` to
the deactivated customer's id (traceable to who triggered the cascade) while keeping
`actor.label` honest that the customer didn't cancel the order themselves.

The query gap fix: `AuditRepository.list_for_aggregate(aggregate_type, aggregate_id, ...)`,
not `list_for_org` — every entry is reachable by the thing it happened to, with no tenancy
anchor assumed. A composite index on `(aggregate_type, aggregate_id, created_at)` backs it.

`AuditLogOrm.id` uses `sa.Identity()` (a real Postgres sequence), not the `HumanFriendlyId`
every other aggregate's id uses: an append-only log with no growth ceiling is exactly the
case a random-10-character scheme isn't sized for — verified against `sona-sso-backend`'s
own `audit/adapters/orm.py` docstring, same reasoning, same choice.

---

## 15. Testing strategy

| Layer | What | How | Speed |
|---|---|---|---|
| `domain/`, `services/` unit tests | Aggregate invariants, application-service orchestration | **Fakes**, not mocks — an in-memory `FakeRepository[T]` implementing `Repository[T]` (`sona`'s `fake_*_repository.py` convention). | Milliseconds |
| `adapters/` integration tests | ORM mapping, repository queries, UoW transaction/rollback | Real PostgreSQL via **testcontainers** — never SQLite, never a mocked `Session`. | Seconds |
| `entrypoints/` e2e tests | Full route → service → repository → DB round trip | FastAPI `TestClient` against the same `app` object `mangum.Mangum` wraps, real Postgres | Seconds |

`uow.outbox` and event publication are **no-op in `LOCAL`/`TEST`** environments (`sona`'s
pattern), so integration/e2e tests never mock SNS/SQS to stay hermetic; assert against the
`outbox_events` table's rows directly.

### 15.1 Where tests live: one top-level `tests/` tree, never nested under `src/`

A subcontext's `tests/` directory living *inside* `src/backend/<product>/<subcontext>/` is a
packaging bug, not a style choice: `[tool.hatch.build.targets.wheel] packages =
["src/backend"]` (or the equivalent setuptools/poetry package-discovery config) packages
*everything* under that path, test code included — the production wheel ships fakes and
assertions alongside real code. Found building the template's own first draft, which had
exactly this.

Verified against `sona-sso-backend`'s real layout: a single `backend/tests/` tree, sibling
to the package it tests, mirroring the package's full path underneath:

```
tests/
├── unit/backend/<same path as src/backend/...>/       # fakes.py + test_*.py, no I/O
├── integration/backend/<same path>/                    # real Postgres via testcontainers
└── e2e/                                                 # FastAPI TestClient, full round trip
```

`pyproject.toml`: `testpaths = ["tests"]` (not `["src/backend", "tests"]`), `pythonpath =
["src", "."]` — the `.` so `tests` itself resolves as an importable package (`from
tests.unit.backend.commerce.stock.fakes import FakeStockRepository`), the same way `src`
makes `backend` resolve. Every directory in the mirrored path needs its own `__init__.py`,
matching `sona-sso-backend`'s tree exactly (it has none of the shortcuts pytest's rootdir
auto-insertion would otherwise tempt you to skip).

---

## 16. Architecture enforcement — import-linter contracts

Both real Postgres-backed codebases studied enforce these with `import-linter` in CI, not by
convention. Applied **uniformly** to every product/subcontext — `sona-sso-backend` only
covered 2 of 4 contexts with the layering contract; don't repeat that gap, template contract
generation for every new subcontext:

1. **Domain purity**: nothing under `domain/` may import `fastapi`, `sqlalchemy`, `boto3`,
   or `httpx`.
2. **Layering, within a subcontext**: `services` may import `adapters` and `domain`;
   `adapters` may import `domain` but not `services`; `domain` imports neither.
3. **Context independence**: no subcontext imports another subcontext's `domain` or
   `services` directly — only via a product's local `commons/` (§3.2), a synchronous port
   (§10.2b), or an event (§11).
4. **Commons independence**: `commons` (global or product-local) imports no product/subcontext.
5. **Entrypoint thinness**: `entrypoints/` may import `services` and `commons`, never its
   own product's `domain.model.aggregate`/`adapters` directly. **Two deliberate exceptions,
   both found while building the template:**
   - A **different product's `domain.model.events`**: an event-consumer entrypoint (§9.4)
     needs the producing product's `IntegrationEvent` class to deserialize against, and
     that's exactly what promoting a `DomainEvent` to `IntegrationEvent` is *for* (§11.1) —
     it's the public contract a consumer is meant to import.
   - **A subcontext's own port-implementing adapter module** (`orders/adapters/pricing_adapter.py`,
     `orders/adapters/user_profile_adapter.py`) — the entrypoint is the composition root
     (§9.1): it constructs the concrete adapter and threads it into a service/orchestrator
     call as a required keyword argument, exactly what bold's own
     `entrypoints/web/breb/breb_credibanco.py` does by importing
     `breb_cashin_pricing_adapter` directly. This is narrower than "the whole `adapters`
     package": `adapters/repository.py` (and `.orm`) stay forbidden — persistence is the one
     thing an entrypoint may never reach past the service layer for; only the outbound-port
     adapters (external HTTP clients, not the database) are allowed through, and only for
     construction, never for calling `uow.repo(...)`-equivalent methods directly.

   `domain.model.aggregate` from either the same or a different product stays forbidden
   either way; only the event contract and the port-adapter *construction* cross.
6. **Orchestrator thinness** (§10.2, §1.5): a product-level `services/*_orchestrator.py`
   file, and everything under top-level `orchestrators/`, may import other subcontexts'
   `services` modules and `commons` — **never** any subcontext's `domain.model.aggregate`,
   `domain.model.events`, `domain.model.rules`, or `adapters` — and never calls
   `uow.repo(...)` or an aggregate command method directly. This is the rule that makes §1.5
   enforceable by tooling instead of by code review vigilance alone.

   **Two narrow, deliberate exceptions to "never `domain.model.*` from a sibling
   subcontext":**
   - `domain.model.value_objects` (found running this standard's own eval benchmark) —
     typed IDs and other value objects, **purely to type-hint a parameter it passes straight
     through**, e.g. `order_id: "order_value_objects.OrderId"` in
     `confirm_order_orchestrator.py` (§10.2).
   - `domain.model.ports` (found building the template's `confirm_order_orchestrator.py`,
     §8/§10.2b) — a port ABC (`UserProfilePort`), **purely to type-hint a caller-supplied
     adapter the orchestrator calls directly but never constructs**: the entrypoint (§9.1)
     builds the concrete adapter and passes it in; the orchestrator only ever sees the
     abstract port type. This is *not* the same as importing `adapters` (still forbidden
     below) — a port is a domain-declared abstraction, not the concrete I/O implementation.

   The rule this contract enforces is "never bypass the service layer's business logic," not
   "never reference a type name from another subcontext" — neither a value object nor a port
   ABC carries an invariant the orchestrator could violate by merely naming it in a
   signature, since the orchestrator still does all actual persistence work by calling the
   owning subcontext's own service function, and all actual I/O by calling a method on a
   port instance it received, not one it built. The line stays sharp: `value_objects` and
   `ports` for typing/pass-through, never `aggregate`/`events`/`rules`/`adapters` for
   anything.

### 16.1 A real `import-linter` gotcha, found by actually running it against the template

`import-linter`'s `forbidden` contract type checks the import graph **transitively by
default** — it doesn't understand "layer L may reach M only through gatekeeper N," it just
asks "is there *any* path from L to M, direct or indirect?" Since `services/orders.py`
legitimately imports `adapters/repository.py` (that's the whole point of the services
layer), a naive contract 5 or 6 flags `entrypoints -> services -> adapters` as a violation
even though the entrypoint never touches `adapters` itself. Both contracts need
`allow_indirect_imports = true` — that setting makes the contract check only *direct*
imports from the source, which is what "don't reach past the gatekeeper" actually means.
Contract 3 (context independence) has the mirror-image trap: list the two subcontexts'
`domain`/`services` sub-modules individually and `orders.services` importing `orders.domain`
(fine — same subcontext) gets flagged as if it were a cross-context violation, because
`independence` treats every listed module as its own sibling. List the two subcontext
*packages themselves* (`backend.commerce.orders`, `backend.commerce.stock`), not their
internal sub-modules, so everything inside one package is one sibling group. The template's
own `.importlinter` file has both fixes applied — copy the shape from there rather than
rediscovering this.

---

## 17. Style guide addendum (Google Python Style Guide specifics)

The full guide applies (https://google.github.io/styleguide/pyguide.html). The points below
are the ones most load-bearing here, cross-checked against real source in `bold` and
`sona-sso-backend` — not assumed.

### 17.1 Import modules, not names — verified, not optional

Google's guide states it plainly: *imports are for packages and modules only, not for
individual classes or functions.* This is not a minor stylistic footnote in this standard —
every code sample above follows it, and it was verified directly against real source before
being written into this document (§0), because an earlier draft of this document got it
wrong throughout.

```python
# WRONG — never do this:
from commerce.stock.domain.model.aggregate import Stock
from commons.adapters.unit_of_work import UnitOfWork

# RIGHT — matches bold's and sona-sso-backend's real source exactly:
from commerce.stock.domain.model import aggregate
from commons.adapters import unit_of_work
...
stock = aggregate.Stock.create(...)
uow: unit_of_work.UnitOfWork
```

**Multi-module imports from one package** are grouped in one parenthesized statement,
verified against `bold`'s real `breb_cashin_management.py`:

```python
from commerce.stock.domain.model import (
    aggregate,
    events,
    exceptions,
    value_objects,
)
```

**Alias on collision, named by role or origin, not mechanically** — verified against real
bold source (`from bold.deposit.breb.commons import value_objects as commons_value_objects`,
`from bold.deposit.deposit.cashin_base.domain.model import aggregate as aggregate_base`):

```python
from commerce.commons import value_objects as commerce_value_objects
from commerce.stock.domain.model import value_objects   # this subcontext's own — no alias needed
```

Also alias when a module name would otherwise shadow a local variable or parameter — see
`commons/domain/aggregates.py` in §5.1, which imports `events` as `domain_events` because
the file's own methods use `events`/`event` as parameter names.

**Three named exceptions**, all verified against real source, none invented for this
document:

1. `typing` and `collections.abc` members may be imported by name (`Annotated`, `Iterator`)
   — Google's own stated exception, confirmed in use in `sona-sso-backend`'s real
   entrypoints.
2. SQLAlchemy's typing/DSL primitives — `Mapped`, `mapped_column`, `DeclarativeBase`,
   `relationship` — may be imported by name; everything else from `sqlalchemy` is imported
   as `sa` and used qualified (`sa.Text`, `sa.select(...)`). Confirmed against
   `sona-sso-backend`'s real `orm_base.py`.
3. Third-party frameworks with a single well-known top-level module (`fastapi`, `mangum`,
   `pydantic`) are imported bare (`import fastapi`) and used fully qualified
   (`fastapi.Depends`, `fastapi.APIRouter`) — confirmed against real entrypoint files. A
   framework submodule genuinely needed by name (`from fastapi import status`, then used as
   `status.HTTP_201_CREATED`) is the same "import a module, not a name" rule one level down,
   also confirmed in real source.

### 17.2 Logging — one shared logger, not `logging.getLogger(__name__)` per file

Do **not** write `_LOGGER = logging.getLogger(__name__)` in every file — that's the
default Python idiom, but it is not what either real codebase does, and repeating it
everywhere means reimplementing formatting/structure/request-correlation per file instead
of once. Instead, one cached, structured logger, defined once:

```python
# commons/adapters/logs.py
import contextvars
import json
import logging
import os
import sys
from typing import Any

_logger: logging.Logger | None = None
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None,
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname, "logger": record.name,
            "message": record.getMessage(), "module": record.module, "line": record.lineno,
        }
        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        _logger = logging.getLogger(os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "local"))
        _logger.propagate = False
        _logger.setLevel(logging.INFO)
        handler.setLevel(logging.INFO)
        _logger.addHandler(handler)
    return _logger
```

Every other file, everywhere in the codebase:

```python
from commons.adapters import logs

_LOGGER = logs.get_logger()
```

This is `sona-sso-backend`'s real `commons/logs.py`, verified directly, adopted as-is —
one cached logger keyed by the Lambda function name, JSON-formatted, request-ID-aware via a
`contextvars.ContextVar` set by request middleware (§14). `bold`'s equivalent is
`logs.get_lambda_logger()` — same shape, different name; this standard uses
`get_logger()`.

Lazy `%s` formatting always in log calls (`_LOGGER.info("Order [%s] confirmed", order.id)`),
never an f-string in a logging call (it formats even when the level would suppress the
line). Exception *messages*, by contrast, do use f-strings with values in square brackets
(§5.5) — this split is `bold`'s consistent house style, adopted as-is.

### 17.3 Everything else

- **Docstrings**: mandatory on public API surfaces — aggregate factory/command methods,
  application-service functions, port abstract methods, `UnitOfWork` methods. Not required
  on small private helpers (`_to_orm`, `_order_repo`) — `bold`'s own deliberate line.
- **Type annotations**: on every function signature, public or private. `X | None`, never a
  bare `None` default without the union.
- **Reconstructing a value object from a plain scalar** (a path param, a DTO's `str` field):
  direct keyword construction — `OrderId(value=order_id)`, `CustomerId(value=order.customer_id)`
  (both `HumanFriendlyId`-backed, §5.2 — a plain `str`-to-`str` copy, no conversion), or
  `identity.users.value_objects.UserId(value=user_id)` (same reasoning) — never
  `OrderId.model_validate({"value": order_id})`. `model_validate` exists for validating an
  already-dict-/JSON-shaped payload with more than one field (`SessionData.model_validate(payload)`
  in `sona-sso-backend`'s real `entrypoints/web/common/session.py`, deserializing a stored
  multi-field blob); wrapping a single already-known scalar in a dict just to hand it to
  `model_validate` is indirection with no payoff — verified against bold's real entrypoints
  (`DepositId(value=deposit_id)` in `entrypoints/web/backoffice_deposit.py`), which construct
  directly. An earlier draft of this document's own template used the two forms
  inconsistently, with no reasoning behind which call site got which — a tell that the
  `model_validate` form was never actually verified before being written, just copied.
- **Naming**: `snake_case` functions/modules, `PascalCase` classes,
  `_leading_underscore` for module-private helpers, `CAPS_WITH_UNDER` constants. Exception
  classes end in `Error`.
- **No mutable default arguments. No bare `except:`. No `staticmethod`** — a module-level
  function instead.
- **`...` vs. `pass` for an empty body**: `...` marks a **stub** — an abstract method
  (`BusinessRule`, §5.4; `Repository[T]`, §7), a `Protocol` method, a signature whose real
  implementation belongs elsewhere. `pass` marks a body that is **genuinely finished** — a
  concrete class with nothing to add beyond its base (`StockId(UuidV7Id): pass`, §5.2;
  `Base(DeclarativeBase): pass`, §7). Using `pass` on an abstract method reads as "this
  method does nothing" when it actually means "implement this"; using `...` on a complete
  concrete class reads as an unfinished stub when nothing is missing. Get this backwards and
  a reader — human or AI — draws the wrong conclusion about whether there's work left to do.
- **`enum.StrEnum` (3.11+), not `class X(str, enum.Enum):`**. The old mixin form's `str()`
  returns `"ClassName.MEMBER"` instead of the raw value unless every consuming class
  remembers to override `__str__`; `StrEnum` gets this right natively. `bold`'s own
  `Currencies` still uses the old mixin form — not a reason to copy it here: this standard
  targets Python 3.13 (§2), where `StrEnum` has been available for three releases.
- **`enum.auto()`, never a value retyped by hand, for any `StrEnum` whose values are its own
  member names** — lowercase or uppercase, both are covered, never just "the lowercase
  case." `StrEnum` overrides `_generate_next_value_` to produce the lowercased member name,
  so `PENDING = enum.auto()` on a plain `enum.StrEnum` already gives `.value == "pending"`
  (§5.3's `OrderStatus`). For the uppercase case — ISO-4217 currency codes, unit codes,
  anything where lowercasing would silently produce the wrong value — `commons/domain/enums.py`
  defines `UpperStrEnum(enum.StrEnum)`, overriding `_generate_next_value_` to return the
  member name unchanged instead of lowercased:

  ```python
  # commons/domain/enums.py
  class UpperStrEnum(enum.StrEnum):
      @staticmethod
      def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str:
          return name


  # commons/domain/money.py
  class Currencies(enums.UpperStrEnum):
      COP = enum.auto()   # .value == "COP"
      USD = enum.auto()
  ```

  Neither base is "more correct" than the other — pick by what the value actually needs to
  be, uppercase or lowercase, and never type the string out by hand for either case. An
  earlier draft of this document had `Currencies` use plain `enum.StrEnum` with explicit
  `COP = "COP"` values, reasoning "auto() only lowercases, so it can't be used here" — true
  of plain `StrEnum` alone, not of the two-line `UpperStrEnum` override needed to cover the
  other case; not reaching for it wasn't a correctness bug, just an incomplete rule.
- **Email format validation: `pydantic.EmailStr` (the `email-validator` package), never a
  hand-rolled regex.** Verified as real, widespread bold precedent — `pydantic.EmailStr` is
  used directly on over a dozen of bold's real DTOs/models, never a custom pattern. An
  earlier draft of this document's own `identity.users.value_objects.Email` used
  `re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")`, which is both looser than the real spec (it
  accepts `a..b@sub..domain.com` — consecutive dots are invalid — `EmailStr` correctly
  rejects it) and reinvents something `email-validator` already gets right. Since `Email` is
  a domain `ValueObject` built deep inside `User.register()`, not a request-body field
  FastAPI parses directly, a bare `EmailStr` field would raise `pydantic.ValidationError` on
  failure — a type `commons.adapters.api.exception_handler` (§13) doesn't know how to map,
  so it would surface as an unhandled 500 instead of a clean 422. The fix keeps `Email.value: str`
  and delegates to `EmailStr`'s validation from inside a `field_validator`, catching its
  failure and re-raising this codebase's own `exceptions.ValidationError`:

  ```python
  # identity/users/domain/model/value_objects.py
  _EMAIL_ADAPTER = pydantic.TypeAdapter(pydantic.EmailStr)


  class Email(value_objects.ValueObject):
      value: str

      @pydantic.field_validator("value")
      @classmethod
      def _validate_format(cls, value: str) -> str:
          try:
              return _EMAIL_ADAPTER.validate_python(value)
          except pydantic.ValidationError as exc:
              raise exceptions.ValidationError(
                  f"[{value}] is not a valid email address.", code="INVALID_EMAIL"
              ) from exc
  ```

  Same reasoning as the `UserProfile`/`AuthResponseBody` dataclass-vs-Pydantic case above:
  reach for the framework's real validation machinery, but keep it behind this codebase's
  one exception vocabulary (§13) rather than letting a foreign exception type leak through.
- **`dataclasses.dataclass(frozen=True)` vs. a `ValueObject`/Pydantic model**: a Pydantic
  model exists to validate and (de)serialize data that crosses a real boundary — parsed from
  JSON, persisted, sent over HTTP. A plain frozen `dataclass` is for an immutable,
  in-process-only structure built directly in Python code that never crosses such a
  boundary — `EventConsumer` (§9.4), pairing an event class with a handler function, is
  exactly that: neither a `type` nor a `Callable` is something Pydantic validates against
  external input in the first place, so reaching for `ValueObject` there would add
  validation machinery with nothing for it to validate.

  **A port's return type is the opposite case, not a look-alike of `EventConsumer`.**
  `UserProfilePort.get_profile`'s `UserProfile` (§10.2b) *is* data that crossed a boundary —
  the adapter parsed it out of an HTTP response — one hop before it reaches the port's
  caller; it just doesn't validate it *again* itself. An earlier draft of this document's own
  template made `UserProfile` a `dataclass`, reasoning from `EventConsumer`'s rule without
  re-checking it against the actually comparable bold precedent: `AuthResponseBody`
  (`bancolombia_cardless_cashout/value_objects.py`), assembled from an already-parsed auth
  response and handed to application code exactly like `UserProfile` is, is
  `base_types.ValueObject` — Pydantic, not a dataclass. So is every one of bold's real
  `output_dtos.py` shapes. The dividing line is "was this ever assembled from parsed
  external input," not "does this specific line of code call `.model_validate()` again."
- **Formatting**: delegate entirely to `ruff format`; configure `ruff.toml` once, stop
  thinking about line length.

---

## 18. Migrations (Alembic)

- Single `migrations/` directory, one physical database, `target_metadata = orm_base.Base.metadata`
  — one shared metadata object, many logical bounded contexts (`sona`'s deliberate choice,
  fine for a single-database deployment).
- **Autogenerate only.** Every migration keeps Alembic's default
  `<12-hex-revision>_<slug>.py` naming. `sona` has hand-named exceptions from bypassing this
  under deadline pressure — the cautionary example, not a precedent. A genuine hand-authored
  data migration still goes through `alembic revision` (scaffolded, then hand-filled), never
  a loose script.
- Cron jobs (§9.5) are housekeeping, not migrations, and don't touch this directory.

---

## 19. The golden-path reference example

The template project (`template/` in this repo) implements this standard end-to-end:

- **`identity/users/`** — registration, login, RS256 JWT issuance (§9.3), refresh-token
  storage/revocation in Postgres. Emits `UserRegistered`, `UserDeactivated`
  (`IntegrationEvent`).
- **`commerce/orders/`** + **`commerce/stock/`** — `Order` (with `OrderLine` as a value
  object, matching the book — not a separate aggregate; each `OrderLine` carries a
  `unit_price: money.PositiveMoney` snapshotted at order-creation time, §5.7), `Stock`
  (deliberately separate, §10.4, price-free — inventory quantity is its only concern).
  Demonstrates: single-aggregate use case (§10.1); same-product multi-aggregate
  orchestration calling services only (§10.2); external synchronous port (§10.2a, now doing
  real work — fetching the current unit price for a SKU); internal synchronous port
  (§10.2b); cross-product **eventual-consistency** reaction via the shared
  `commons.adapters.sqs.process_sqs_event` dispatcher, idempotent (§9.4/§12.2) — this golden
  path's one cross-product relationship turned out to be exactly this, not §10.3's
  synchronous top-level-orchestrator tier (§10.3 explains why, and what a genuine instance
  of that tier would need instead); a cron entrypoint (§9.5/§18); `Order.total` as a derived
  `@property`, never a stored field (§5.7).
- **`commerce/commons/`** — `Sku`, shared between `orders` and `stock` (§3.2).
- **`commons/domain/money.py`** — `Money`/`NonNegativeMoney`/`PositiveMoney` (§5.7), ported
  from `bold`, used wherever the template needs an amount of currency.

Every code sample in §5–§13 is drawn from, and kept in sync with, this template — if they
disagree, the template is the bug.

---

## 20. Anti-patterns and lessons learned

| Anti-pattern | Where it was found | What this standard does instead |
|---|---|---|
| Domain events recorded, never drained | `sona-sso-backend` — `pull_events()` defined, never called | §1.6 makes this review-blocking; §11.2 mandates the outbox as the drain point |
| Publish-after-commit with no durability guarantee | `sona` — event lost if the process dies between commit and publish | §11.2 — outbox row written in the same transaction as the aggregate |
| No idempotency layer for event consumers | `sona` — Standard SQS, no dedup table, `BaseEvent.attempts` fields present but unread | §12.2 — the same `idempotency_keys` table as §12.1 + `idempotence_key()`, mandatory on every event handler |
| Three coexisting generations of "shared" code | `sona` — `shared_package`→`sona_common`→`common`, all three still attached to every Lambda | §14 — exactly one global `commons/`, extend it, never fork it |
| UoW subclass per Lambda composition root | `sona-sso-backend` — an ad hoc matrix, flagged as unresolved in its own `CLAUDE.md` | §8 — one generic `UnitOfWork` with a repository registry |
| Orchestrator reaching past services into aggregates/repos | Not found in `bold` (its orchestrators get this right) — flagged here because an earlier draft of *this* document got it wrong | §1.5, §10.2, import-linter contract 6 — enforced, not just written down |
| `datetime` columns instead of epoch integers | Not found in the reference codebases (they already avoid it) — flagged because an earlier draft of *this* document used `Mapped[datetime]` | §1.8, §7 — `PosixTime` + `BigInteger` everywhere, verified against real `orm_base.py` |
| Import-linter contracts applied inconsistently across contexts | `sona-sso-backend` — only 2 of 4 contexts had the layering contract | §16 — contract generation templated per new subcontext |
| A 7,499-line "god aggregate" | `bold`'s core `Deposit` aggregate, ~50 channels' worth of limits in one class | §5.3 — aggregates stay narrow; a 40th `NamedEnum` member is the signal to split, not a feature request |
| In-memory rate limiting under Lambda | `sona`'s `sona_common.middleware.RateLimitingMiddleware` — a plain dict, broken across ephemeral/concurrent containers | Rate limiting belongs at API Gateway or a distributed store, never in-process state |
| Two parallel JWT mechanisms mid-migration | `sona` — legacy HS256 custom-authorizer vs. new RS256, both live | §9.3 documents only the target; no legacy path to carry here |
| Reaching into a value object's internal field to reimplement behavior it already has | `sona-sso-backend`'s own `entrypoints/cron/check_cert_expiry.py` — compares `cert.expires_at.microseconds` by hand instead of using `PosixTime.__lt__` | §1.11, §5.1 — domain/application code calls the VO's own methods; `_to_orm`/`_to_entity` (§7) is the one authorized exception |
| Event-consumer boilerplate hand-rolled per entrypoint file, no dispatch table | Not found in `bold`/`sona` (both centralize it) — flagged because an earlier draft of *this* document hand-rolled a `for record in event["Records"]` loop per file instead of reusing a shared helper | §9.4 — `commons.adapters.sqs.process_sqs_event`, called once per event entrypoint |
| Two hand-maintained mappings (string→class for parsing, class→handler for dispatch) that can silently drift apart | `sona`'s real `event_map`/`event_handlers` pair — `sona`'s own troubleshooting notes list "unmapped event names in `_EVENT_MAP`" as a recurring incident | §9.4/§11.1 — one `EventConsumer` registration list, keyed by `DomainEvent.event_type`, a *computed* field that cannot drift from the class it names |
| Every event handler individually responsible for remembering its own idempotency wrapper | `bold`'s own `_confirm_or_revert_breb_cashin`-style handlers — each opens `with uow.transaction(idempotence_key=...)` and catches `DuplicatedTransactionError` itself | §9.4 — the dispatcher wraps the common case automatically; only handlers that need I/O before their write (documented escape hatch) remain responsible by hand |
| No optimistic concurrency control — two concurrent writes to the same aggregate silently overwrite each other | Not found in `bold` (it has real version checking via DynamoDB conditional writes) — flagged because an earlier draft of *this* document defined `AggregateRoot` and the `UnitOfWork` with no version field and no conflict detection at all | §5.1/§8.1 — `AggregateRoot.version` + SQLAlchemy's native `version_id_col`, raising `ConcurrentModificationError` on a lost race |
| Contract 6 read literally as "an orchestrator may never import a sibling subcontext's `domain/` at all" — even a typed ID/value object used only to type-hint a pass-through parameter | Surfaced by the skill's own eval benchmark: a correct, benchmark-passing orchestrator run imported `domain.model.value_objects` for typing and had no rule covering whether that was allowed | §16 contract 6 now carves out `value_objects` explicitly (typing only), while keeping `aggregate`/`events`/`rules`/`adapters` strictly off-limits |
| `self.updated_at = PosixTime.now()` repeated inline at the end of every command method | `bold` — this exact line appears in nearly every aggregate's command methods across the codebase, never generalized | §5.1/§5.3a — `AggregateRoot.touch()`, one base-class method, called instead of repeating the assignment |
| A status field updated by direct `if status is not X: raise; self.status = Y` checks scattered per command, instead of one declared table of legal transitions | Not found missing in `bold` (its real `_change_status` + `_STATUS_TRANSITIONS` dict already does this) — flagged because an earlier draft of *this* document's `Order` aggregate didn't, despite citing bold's pattern elsewhere | §5.3a — a module-level `_ORDER_STATUS_TRANSITIONS` dict + a private `_transition_status` choke point, the same shape as bold's `bancolombia_cardless_cashout/aggregate.py` |
| External I/O (a `Port` call) made *inside* an already-open `with uow.transaction():` block | An earlier draft of *this* document's own `services/orders.py::confirm_order` — its sibling `create_order` already fetched external data before opening the transaction, but `confirm_order` didn't, contradicting its own codebase's established rule | §8 (new "No I/O inside an open transaction" subsection) — the fetch moves to whichever function opens the *outermost* transaction, since a nested `uow.transaction()` call is a no-op and can't fix this from the inside |
| A service function silently constructing its own default adapter (`port = pricing_port or pricing_adapter.HttpPricingAdapter()`) instead of requiring the port as a parameter | An earlier draft of *this* document's own `services/orders.py` — bold's real `x or DefaultAdapter()` pattern only appears inside a class's own `__init__`, never inline in a plain service function called per request; every real bold service function threading a port makes it a **required** kwarg, composed at the entrypoint | §9.1/§10.2a — the entrypoint is the composition root; a private `_get_pricing_port()` factory there, never a fallback inside the service |
| Two independent bounded contexts (`orders`, `stock`) routed through one combined `entrypoints/web/public.py` file/Lambda | An earlier draft of *this* document's own template — contradicted its own §10.4 (orders/stock are deliberately separate contexts) and `sona-sso-backend`'s real practice of one router file per subcontext, even inside a Lambda that legitimately composes several | §9.1 — one file per subcontext (`orders.py`, `stock.py`), each its own `app`/`mangum.Mangum(app)` |
| A bare integer HTTP status code (`status_code=201`) instead of `fastapi.status.HTTP_201_CREATED` | An earlier draft of *this* document's own template, in three call sites | §9.1/§17.1 — `from fastapi import status`, then `status.HTTP_201_CREATED`, matching every real `sona-sso-backend` router file |
| An HTTP adapter method with no retry on transient network failures, and parsing `response.json()` by raw dict-key access instead of a typed response schema | An earlier draft of *this* document's own `pricing_adapter.py`/`user_profile_adapter.py` — bold's real `bancolombia_cardless_cashout/adapter.py` has both `@backoff.on_exception(...)` and a `mappers.map_response_to_...` split into a typed DTO first | §10.2a — `backoff.on_exception(backoff.expo, ..., jitter=backoff.full_jitter, max_tries=3)` + a `_*ResponseDTO(pydantic.BaseModel)` parsed before conversion to the domain type |
| `OrderId(value_objects.UuidV7Id)`, contradicting this same document's own §5.2 rule ("use `HumanFriendlyId` only when the ID is genuinely user-facing") in the very example meant to illustrate it | An earlier draft of *this* document's own template — `Order` is exactly the "a customer reads this off a receipt" case bold's real `LoanId`/`CashoutId` (both `HumanFriendlyId`) demonstrate | §5.2 — `OrderId(value_objects.HumanFriendlyId)`; `StockId` correctly stays `UuidV7Id` |
| `identity.users.UserId(value_objects.UuidV7Id)`, reasoned only against bold's fintech aggregates, never checked against `sona-sso-backend`'s own identity aggregates — the actually comparable precedent, being an identity backend itself | An earlier draft of *this* document's own template — `sona-sso-backend`'s real `ConsoleUserId`/`OrganizationId`/`SsoConnectionId` are all `HumanFriendlyId` | §5.2 — `UserId(value_objects.HumanFriendlyId)`, and `commerce.orders.CustomerId` follows it (it mirrors `UserId`'s real value, §10.3) — a cascading consequence traced through by hand, not caught by any tool: `CustomerId(value: uuid.UUID)` type-checked fine right up until a real `HumanFriendlyId` string reached `uuid.UUID(...)` and raised `ValueError` at runtime |
| A hand-rolled email regex (`^[^@\s]+@[^@\s]+\.[^@\s]+$`) instead of `pydantic.EmailStr` — looser than the real spec (accepts `a..b@sub..domain.com`, consecutive dots and all) | An earlier draft of *this* document's own `identity.users.value_objects.Email` — bold uses `pydantic.EmailStr` directly on over a dozen real DTOs/models, never a custom pattern | §17.3 — `EmailStr`'s validation, wrapped in a `field_validator` that re-raises this codebase's own `exceptions.ValidationError` (so a malformed email still surfaces as the established 422, not `EmailStr`'s raw `pydantic.ValidationError`, which `exception_handler.py` doesn't know how to map) |
| A top-level orchestrator (`orchestrators/deactivate_user_cascade.py`) that unconditionally forwarded to exactly one service function — a Middle Man (§22.2), not real cross-product orchestration, presented as §10.3's own flagship example | An earlier draft of *this* document's own template — caught by asking "why is this an orchestrator if it only calls one aggregate?", not by any tool (import-linter contract 6 has nothing to say about an orchestrator that legitimately imports only one subcontext's services — the smell is behavioral, not structural) | §10.3/§22.2 — deleted; `entrypoints/web/public.py` calls `auth.deactivate_user` directly (§10.1, single-aggregate); `orchestrators/` stays empty in this golden path, a real extension point rather than a forced example |
| One `Repository[T].put()` covering both insert and update via `session.merge(...)`, unable to express collision-retry on a `HumanFriendlyId` insert at all | An earlier draft of *this* document's own template — `sona-sso-backend`'s real `OrganizationRepository` has separate `add()`/`update()` methods, never one unified `put` | §7 — `Repository[T].add`/`.update`, matching the real interface |
| A `pydantic-settings` dependency declared (`pyproject.toml`) and never used — hand-rolled `os.environ.get(...)` reads in `commons/adapters/settings.py` instead, plus `os.environ[...]` scattered directly in two HTTP adapters and an entrypoint, `INTERNAL_API_KEY` duplicated across two of them with nothing declaring it required in one place | An earlier draft of *this* document's own template — `sona-sso-backend`'s real `commons/settings.py` is `pydantic_settings.BaseSettings`, one class, one vocabulary | §14.1 — `Settings(pydantic_settings.BaseSettings)`, every env var validated once at `get_settings()`; every scattered `os.environ[...]` read replaced with a call through it |
| A collision-retry helper that calls plain `session.rollback()` on a failed insert attempt, which rolls back the *entire* outer transaction (discarding every other write already staged in it), not just the one failed insert | An earlier draft of *this* document's own `insert_with_id_retry` — `sona-sso-backend`'s real version uses `session.begin_nested()` (a SAVEPOINT) specifically to scope the rollback to one attempt | §7.1 — `with session.begin_nested(): ...` around each retry attempt |
| A domain event's recorded events drained and published by a hand-called `_publish_events()` helper in every `services/*.py` function — easy to forget on a new use case | An earlier draft of *this* document's own template, in every subcontext's services module — contradicts bold's own documented lifecycle ("`save(aggregate)` calls `uow.publish(event)` inside a transaction," `lambdas/CLAUDE.md`) | §7 — `Repository[T].add`/`.update` publish internally via `repository_helpers.publish_events`; a service can no longer forget |
| An orchestrator comparing a DTO's status field against a raw string (`order.status == "confirmed"`) to decide whether to release stock, instead of asking a named question | An earlier draft of *this* document's own `services/cancel_order_orchestrator.py` | §22.1 — Tell, Don't Ask: `Order.had_reserved_stock`, a property `cancel_order` captures before mutating and threads through the DTO |
| `uow.repo(aggregate.X)` resolved as the first statement of a function, one line *before* `with uow.transaction():` opens | An earlier draft of *this* document's own `services/orders.py`/`services/stock.py`/`services/auth.py` — `UnitOfWork.repo` reads `UnitOfWork.session`, which raises `RuntimeError` until a transaction is actually open (§8) | §6 — the repository is always resolved as the first statement *inside* the `with` block |
| `uow.repo(aggregate.X)` called twice in the same function (once for a read, again for the write) instead of once, cached in a local variable | An earlier draft of *this* document's own `services/orders.py`/`services/auth.py` — not a correctness bug (the UoW memoizes the repository instance), but two separate-looking calls read as two separate concerns where there's only one | §6 — resolve the repository once per function, reuse the local variable for every subsequent call |
| DTO output fields typed as bare `str` for what is really an enum (`status: str`, `currency: str`), populated via `.value` — nothing stops a typo or an unvalidated value from flowing through | An earlier draft of *this* document's own `OrderOutputDTO`/`OrderLineOutputDTO` | §5.2/§6 — `status: value_objects.OrderStatus`, `currency: money.Currencies`; Pydantic rejects an invalid value at construction, and `StrEnum` still serializes to the plain string over the wire — no change to the API response |
| Reconstructing a value object from a plain scalar via `Foo.model_validate({"value": x})` in some call sites and direct `Foo(value=x)` in others, with no reasoning behind which got which | An earlier draft of *this* document's own template — 6 call sites used `model_validate`, 10 others in the same codebase already used direct construction correctly | §17.3 — always direct keyword construction for a single already-known scalar; `model_validate` is for an already-dict-shaped multi-field payload, verified against bold's real entrypoints and `sona-sso-backend`'s real `SessionData.model_validate(payload)` (the one legitimate use of the pattern) |
| `# type: ignore` reached for before the actual type was fixed — an untyped `sns_client: object`, a registry typed `type[Repository[Any]]` when the real contract was a `Callable`, a `Protocol` missing one attribute it could have declared, a union-of-different-arity-callables dispatched by runtime introspection | An earlier draft of *this* document's own template — 4 separate ignores, each fixable by typing the real thing instead of the escape hatch | §2.1 — `mypy_boto3_sns.client.SNSClient`, `Callable[[Session], Repository[Any]]`, `id: str` on the Protocol, and splitting `EventConsumer.handle` into two mutually-exclusive fields (§9.4); the one ignore that's a genuine, verified mypy/pydantic limitation (`computed_field` + `@property`) stays, narrowly scoped |
| `UserProfile` (a port's return type, §10.2b) made a `dataclass`, reasoning from `EventConsumer`'s dataclass rule (§17.3) without re-checking it against the actually comparable bold precedent | An earlier draft of *this* document's own template — bold's real analog, `AuthResponseBody` in `bancolombia_cardless_cashout/value_objects.py` (also adapter-output data handed to application code), is `base_types.ValueObject` — Pydantic, not a dataclass | §17.3 — `UserProfile(value_objects.ValueObject)`; the dividing line is whether the data was ever assembled from parsed external input, not whether this specific line re-validates it |
| A `StrEnum`'s member values typed out by hand (`PENDING = "pending"`, `COP = "COP"`) when the value is just the member name, upper- or lowercased | Not a bug, a missed simplification, in two stages: first `OrderStatus` (lowercase case) was fixed with plain `StrEnum.auto()`; `Currencies` (uppercase case) was initially left as explicit values with a comment saying `auto()` "can't" cover it, until the same pattern from a prior project (`agroconecta`'s real `UpperStrEnum`) was pointed out | §17.3/§5.3/§5.7 — `PENDING = enum.auto()` on plain `enum.StrEnum` for the lowercase case; `commons/domain/enums.py`'s `UpperStrEnum` (overriding `_generate_next_value_` to return the name unchanged) plus `COP = enum.auto()` for the uppercase case. Two small, symmetric bases, not one rule with an unhandled half |

Several rows above are marked as flagged because an earlier draft of *this* document got
them wrong, deliberately — this table stays honest about this document's own mistakes once
a human reviewer caught them, not only about the three source codebases.

---

## 21. Glossary

| Term | Meaning here |
|---|---|
| **Product** | Top-level business capability grouping (`identity`, `commerce`). |
| **Subcontext** | A bounded context proper — owns exactly one aggregate concept, named after it (§3.1). |
| **Aggregate** | A cluster of domain objects treated as one consistency boundary; only the root is referenced from outside. |
| **Value Object** | Immutable, defined by its value, no identity. |
| **Entity** | Has identity (`id`), mutable. |
| **Port** | An abstract interface declared by the domain for an outbound synchronous dependency. |
| **Adapter** | A concrete implementation of a port, or of the generic `Repository` contract. |
| **Domain event** | A fact recorded by an aggregate, internal to its bounded context unless promoted. |
| **Integration event** | A domain event's public, versioned representation, published via the outbox. |
| **Orchestrator** | A function coordinating multiple subcontexts' `services/` functions — product-level (atomic) or top-level (eventual consistency). Never touches `domain/`/`adapters/` directly (§10, contract 6). |
| **Outbox** | A table written in the same transaction as an aggregate mutation, later relayed to the message broker. |
| **UoW (Unit of Work)** | The transaction-boundary abstraction; one generic class, resolves repositories by aggregate type. |
| **PosixTime** | Integer-microseconds-since-epoch value object; the only timestamp representation used, domain or database (§1.8). |
| **Optimistic concurrency** | Detecting a lost write-write race by version-checking at write time rather than locking at read time — `AggregateRoot.version` + SQLAlchemy's `version_id_col`, raising `ConcurrentModificationError` (§8.1). |

---

## 22. Design principles and code smells reference

Every non-obvious structural rule in this document traces back to a named OOP principle or
a named code smell — not a personal preference. This section makes those names explicit and
points each one at the exact place in this document where it's applied, so a future
disagreement can be argued in those terms instead of re-litigated from scratch. Terminology
and refactoring techniques below follow the standard classification (Fowler /
refactoring.guru), the same one used in this document's own author's OOP course material —
cited by file, not paraphrased from memory, wherever a specific example is drawn from it.

### 22.1 Code smells actively designed against

| Smell | Refactoring technique | Where this document applies it |
|---|---|---|
| **Message Chains** (`a.getB().getC().getD()` — the smell name for what's commonly called a Law of Demeter violation) | Hide Delegate | §1.11 / §5.1: domain and application code call a value object's own methods (`PosixTime.__lt__`, `Money.compare`) instead of chaining into `.microseconds`/`.value`. `adapters/repository.py`'s `_to_orm`/`_to_entity` (§7) is the one authorized exception — a Data Mapper's whole job is bridging two representations, not a chain a caller stumbled into. |
| **Feature Envy** (a method more interested in another class's data than its own) | Move Method | §5.7: `Order.total` is a method *on* `Order`, computed from `self.lines` — the alternative (an external `OrderTotalCalculator` reaching into `order.lines` from outside) would be textbook Feature Envy over data `Order` already owns. |
| **Inappropriate Intimacy** (two classes reaching into each other's internals instead of going through a public contract) | Move Method / encapsulate the state | §1.5 / §10.2: an orchestrator calling `uow.repo(Stock)` and mutating `stock.available_quantity` directly — instead of calling `stock_service.reserve_stock(...)` — is this smell, precisely: reaching past `Stock`'s own service into its internals. Import-linter contract 6 (§16) makes it a build failure, not just a code-review catch. |
| **Switch Statements** (branching repeatedly on an object's "type") | Replace Conditional with Polymorphism | §13's `_STATUS_FOR` mapping and §9.4's `EventConsumer` registry are deliberate **dictionary-dispatch**, not `if/elif` chains keyed on event or error type — the same motivating problem (a new case forces editing an existing conditional instead of adding a new registration) without requiring a full class hierarchy where one isn't otherwise needed. Narrow, named exceptions per invalid transition (§5.5) are the same idea one level up: `InsufficientStockError` is its own class specifically so nothing downstream needs a `match error.code:` block to know what happened. |
| **Refused Bequest** (a subclass inherits behavior it doesn't want, and overrides it just to reject it) | Reorganize the hierarchy | Cited as the reason `commons.domain.entities.Entity[IdT]` stays minimal (identity + timestamps only) rather than a fatter base class every aggregate would have to override away unwanted behavior from. |
| **Tell, Don't Ask** (a caller inspects an object's state to make a decision the object itself should make) — not strictly a Fowler "smell" name, but the same family as Feature Envy/Message Chains above | Move the decision into a query method on the object that owns the state | `Order.had_reserved_stock` (§5.3a): `services/cancel_order_orchestrator.py` asks `cancelled_order.had_reserved_stock` — a named question `Order` itself answers (`self.status is OrderStatus.CONFIRMED`) — instead of comparing `order.status == "confirmed"` against a magic string itself, which an earlier draft of *this* document's own template did. The orchestrator tells `orders.cancel_order` to cancel and asks what happened; it never re-derives the answer from raw state it peeked at externally. |

### 22.2 A smell this document deliberately does *not* over-correct: Middle Man

**Middle Man** — a class whose methods only forward to another object, adding no behavior —
is the failure mode on the *other* side of Hide Delegate and Inappropriate Intimacy: fixing
one of those two by wrapping every call in a pass-through layer recreates this one. Two
concrete guardrails already in this document exist for exactly this reason:

- §10.1 says explicitly: a single-aggregate use case is called directly, with **no**
  orchestrator wrapping it "for symmetry." An orchestrator that only forwards one call to one
  service function, unconditionally, is a Middle Man — delete it. Not hypothetical: §10.3's
  own flagship example, an earlier draft's `orchestrators/deactivate_user_cascade.py`, was
  exactly this — one unconditional forward to `auth.deactivate_user` — until asking "why is
  this an orchestrator if it only calls one aggregate?" caught it. Deleted; the entrypoint
  calls `auth.deactivate_user` directly now.
- `DefaultStockRepository` (§7) implements `Repository[T]` directly; this document does not
  interpose a second "service" layer between the repository and its one caller
  (`services/stock.py`) that would do nothing but rename `add`/`update`/`get_by_sku` to
  something else. A layer earns its place by owning a rule, a translation, or a transaction
  boundary — not by existing between two other layers.

### 22.3 SOLID principles this architecture is built from

| Principle | Where |
|---|---|
| **Single Responsibility** | The whole `domain/model/` → `domain/services/` → `services/` → `adapters/` → `entrypoints/` split (§4) is one responsibility per layer: business rules, cross-aggregate pure logic, use-case orchestration, persistence translation, transport. |
| **Open/Closed** | New bounded contexts, new event consumers (§9.4's `EventConsumer` registry), new external adapters (§10.2a) are all *additions* to a list/registry, never edits to existing dispatch code. |
| **Liskov Substitution** | §5.1 documents this by name: narrowing `id: EntityId` to `id: StockId` in a subclass is the same category of violation as the canonical car-hierarchy example (a subclass changing a method's return type breaks every caller that trusted the base type's contract) — PEP 695 generics (`Entity[IdT]`) are the fix that requires no exception to the rule anywhere. |
| **Interface Segregation** | Every port (§5.6) is narrow and single-purpose (`PricingPort` does pricing, nothing else) — never one fat `ExternalServicesPort` a subcontext would have to depend on in full to use one method of. |
| **Dependency Inversion** | The entire Ports & Adapters shape (§5.6, §10.2) *is* DIP: `orders/services/orders.py` (high-level) depends on `PricingPort` (an abstraction it owns), never on `orders/adapters/pricing_adapter.py` (the low-level detail) directly — structurally identical to a `NotificationService` depending on an abstract `Notifier` rather than a concrete `EmailNotifier`. Swapping the concrete pricing adapter never touches the service that uses it, by construction. |

---

## 23. Contribution workflow — branch, commit, PR

Neither `bold` nor `sona-sso-backend` documents branch naming, commit message format, or a
PR checklist anywhere in either real repo — checked directly, not assumed (no
`CONTRIBUTING.md`, no `.github/pull_request_template.md`, no mention in either `CLAUDE.md`).
So unlike almost everything else in this document, this section has no real-code precedent
to verify against; it's written fresh for this template, flagged as such rather than
presented as bold/sona convention it isn't.

The actual content — branch naming (`nombre.apellido/tipo/TICKET-123-descripcion-corta`),
commit format (`tipo: #ticket descripción`), the pre-commit hooks that enforce both plus
format/lint/type/import-linter checks, and what CI (`.github/workflows/ci.yml`) re-checks —
lives in `template/CONTRIBUTING.md`, `template/.pre-commit-config.yaml`, and
`template/scripts/check_*.py`, not duplicated here: the same "this document cites, the
template's own files are the source of truth" relationship §19 already describes for every
other code sample in this standard. Run `make hooks` once per clone to install them
(`template/README.md`).

---

## Appendix: source material

- `bold`: `lambdas/bold/deposit/` (application code, incl. `breb/breb_cashin/` — the
  file-by-file source for §5.3, §6, §10.2, §17.1, and `breb/services/apply_and_confirm
  _or_reject_breb_cashin_orchestrator.py` specifically for §10.2's orchestrator-calls-
  services rule), `infra/bold/deposit/` (CDK), `lambdas/bold/commons/` (shared kernel,
  `base_types.py` for §5.1's `Entity`/`AggregateEventAware`, §5.2's non-generic ID typing,
  and `RootEntityVersion`/`RootEntity.version` for §8.1's optimistic concurrency source;
  `commons/adapters/unit_of_work.py`'s `_add_write_operation`/`ConcurrentModificationError`
  for the same), `lambdas/bold/commons/standard_types/money.py` (§5.7), `lambdas/CLAUDE.md`
  / `infra/CLAUDE.md`.
- `sona-sso-backend`: `backend/sona_sso/` (all products), `commons/domain/value_objects.py`
  (`PosixTime`, §5.1), `commons/adapters/orm_base.py` (`TimestampsMixin`, §7),
  `commons/logs.py` (§17.2), `entrypoints/web/organizations.py` (import style, §17.1),
  `entrypoints/cron/check_cert_expiry.py` (the negative example in §1.11/§20),
  `CLAUDE.md`, `docs/ARCHITECTURE.md`.
- `sona`: `modules/*_v2/`, `common/`, `common/infrastructure/events/base_event_handler.py`
  (`BaseSQSEventHandler.process_sqs_event` — the starting point for §9.4, superseded there by
  a design closer to `bold`'s own event-handling code once the two dictionaries it requires
  were identified as the source of `sona`'s own documented "unmapped event names" incidents),
  `ARCHITECTURE_EVENTS.md`, `template*.yaml`.
- Book: [_Architecture Patterns with Python_](https://www.cosmicpython.com/), source at
  `github.com/cosmicpython/book`, chapters 1, 2, 4, 6, 7, 8, and
  `appendix_project_structure`.
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html), especially
  the Imports section (§17.1).
- This document's own author's OOP/design-patterns course material (§22):
  `especializacion_ds/refactoring/05_couplers.ipynb` (Message Chains, Feature Envy,
  Inappropriate Intimacy, Middle Man — §22.1/§22.2), `especializacion_ds/refactoring/
  02_object_orientation_abusers.ipynb` (Switch Statements, Refused Bequest — §22.1),
  `especializacion_ds/solid/liskov.ipynb` and `.../solid/dependency_inversion.ipynb`
  (§5.1, §22.3).
