# Entrypoints and orchestration

> Topic excerpt of `../../../ARCHITECTURE.md` §9–§10. If this file and `ARCHITECTURE.md`
> disagree, `ARCHITECTURE.md` wins. **Read the orchestration decision tree (§10) before
> writing any function that touches more than one aggregate.**

**Contents**: §9.1 web entrypoints (public/internal) · §9.2 why `internal.py` exists ·
§9.3 authentication · §9.4 event consumers (`EventConsumer`, `process_sqs_event`) · §9.5
cron · §10 the orchestration decision tree · §10.1–§10.3 the three tiers · §10.4 the
Order+Stock divergence from the book.

## §9. Entrypoints

### §9.1 Web (`entrypoints/web/{public,internal}.py`)

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

`typing.Annotated` is imported by name — see `enforcement-and-style.md` for the full list of
named import exceptions; everything else (`fastapi`, `mangum`) is a bare module import, used
qualified (`fastapi.Depends`, `fastapi.FastAPI`), exactly matching `sona-sso-backend`'s real
entrypoint files.

- Routers are **thin**: parse input, call exactly one service function, return its DTO. No
  `domain` import here — enforced by import-linter contract 5.
- `public.py`: JWT required by default; exempted routes (`/login`, `/register`) say so
  explicitly in the route, not by omission.
- `internal.py`: service-to-service only, different auth dependency
  (`fastapi.Depends(require_service_auth)` — API key or IAM SigV4). Never accepts a customer
  JWT.
- **One file per subcontext, never two subcontexts sharing a router.** `orders` and `stock`
  are independent bounded contexts (§10.4) with independent deploy/scale lifecycles — a
  combined `public.py` routing both was an early draft's mistake, caught by checking
  `sona-sso-backend`'s real `entrypoints/web/`: `organizations.py` and `sso_connections.py`
  are two files even inside the same product, and even a Lambda that legitimately composes
  both contexts does so by importing each context's already-separate `router`/`*ServiceDep`
  and overriding their UoW binding — never by writing both contexts' routes into one file.
- **Every status code is `fastapi.status.HTTP_*`, never a bare int** — `from fastapi import
  status`, then `status.HTTP_201_CREATED`, not `201`. Verified against every real
  `sona-sso-backend` router file; applies to `status_code=` kwargs and `raise
  fastapi.HTTPException(status_code=...)` alike.
- **A port's concrete adapter is constructed here, never inside the service/orchestrator it's
  passed into, and never as an `x = param or DefaultAdapter()` fallback inside that
  function.** A private module-level factory builds it; the route handler passes it in as a
  required keyword argument:

  ```python
  def _get_pricing_port() -> ports.PricingPort:
      return pricing_adapter.HttpPricingAdapter()

  @app.post("/orders", ..., status_code=status.HTTP_201_CREATED)
  def create_order(body: orders_dto.CreateOrderInputDTO, uow: UowDep, _user: UserDep) -> orders_dto.OrderOutputDTO:
      return orders.create_order(uow=uow, input_dto=body, pricing_port=_get_pricing_port())
  ```

  Verified against bold's real `entrypoints/web/breb/breb_credibanco.py`:
  `_get_breb_cashin_pricing_adapter()` is defined right there and called at each route's call
  site; every service/orchestrator function it feeds declares the port as a **required**
  parameter, never `| None = None` with a fallback default — bold's own `x or
  DefaultAdapter()` pattern only ever appears inside a class's `__init__`, setting an
  instance attribute once, never inline in a plain service function called per request. This
  is also why import-linter's entrypoint-thinness contract has to name an exception (see
  `enforcement-and-style.md`): an entrypoint importing `orders.adapters.pricing_adapter` to
  construct it is the composition root doing its job, not reaching past the service layer —
  `orders.adapters.repository` stays forbidden either way.

### §9.2 Why `internal.py` exists, and what it's for

Not a general cross-context escape hatch. Exists for exactly one reason: another bounded
context needs a point-in-time snapshot of data it must own a copy of. Golden-path example:
`commerce/orders` confirming an order snapshots the customer's name/email/address via
`GET /internal/users/{id}/profile`, so a later profile change doesn't retroactively rewrite
historical orders. It is explicitly **not** used to check "does this user exist / are they
active" — the JWT already proves that (§9.3 below).

### §9.3 Authentication

RS256 JWT, asymmetric. Only `identity/users` holds the private key and signs; the public key
is distributed so any product verifies **locally, with no network call** — what makes §9.2's
"no synchronous existence check" rule viable at all.

- **Access token**: ~15 minutes TTL, validated locally on every request.
- **Refresh token**: long-lived, opaque, stored in `identity/users/adapters/orm.py`
  (Postgres — no second data store), revocable. Revoking it is how a deactivated user's
  session actually dies quickly, with no product ever calling back to `users`.
- `identity/entrypoints/cron/expire_refresh_tokens.py` sweeps expired rows on a schedule.

### §9.4 Events (`entrypoints/events/`)

One handler file per (source topic, consuming product) pair — `sona`'s proven granularity.
The dispatch *mechanics* underneath follow `bold`, not `sona` — `bold`'s `entrypoints/events/*`
handlers receive already-typed events and dispatch by **`type(event)`** through a strategy
map (`bold`'s own `lambdas/CLAUDE.md`: *"Use a strategy map inside `EventHandler`
(`type(event) → ProcessHandler`) to dispatch"*), never by a hand-maintained string. `sona`'s
real `BaseSQSEventHandler.process_sqs_event` needs **two** dictionaries kept in sync by
hand — `event_map: dict[str, type[Event]]` for parsing and `event_handlers: dict[type[Event],
Callable]` for dispatch — and `sona`'s own operational notes list exactly the failure this
invites: *"unmapped event names in `_EVENT_MAP`"* as a recurring incident. This standard
closes that gap by making the event class itself the only source of truth for its wire name
(`DomainEvent.event_type`, `events-idempotency-errors.md`, a *computed* field — it cannot
drift from the class because it *is* the class name), so there is exactly **one** registration
list, not two dictionaries to keep aligned.

It goes one step further than either reference: `bold`'s own handlers still make every
handler function individually responsible for opening
`with uow.transaction(idempotence_key=...)` and catching `DuplicatedTransactionError` — easy
to forget on a new handler. For the common case — a handler with no I/O before its one
write — the dispatcher does the wrapping itself, so there is nothing to forget:

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

    A plain `dataclass`, not a `ValueObject`/Pydantic model — see `enforcement-and-style.md`
    for why: this holds a `type` and a `Callable`, constructed once in Python code at import
    time, never parsed from JSON or any other external input.

    Exactly one of `handle`/`handle_without_uow` must be set — enforced in `__post_init__`.
    Two separate, non-union fields, not one `Callable[[UoW, EventT], None] |
    Callable[[EventT], None]` dispatched by inspecting a handler's parameter count at
    runtime: mypy cannot narrow a union of different-arity callables from a runtime check, so
    that shape needs a `# type: ignore` at every call site that invokes `consumer.handle`
    (`enforcement-and-style.md` §2.1 has the full before/after). Two mutually-exclusive
    fields need none, and the registration call site states its intent directly.
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
(never `domain/` directly) — there is no `with uow.transaction(...):` for it to remember or
forget. `DuplicatedTransactionError` never reaches it; the dispatcher already turned a
duplicate delivery into a log line and a clean return, not an error.

**The escape hatch, for `bold`'s real harder case.** Some handlers genuinely need I/O
*before* they know what to write — `bold`'s `_confirm_or_reject_breb_cashin` calls an
external provider first, and only then decides which of two different write paths to take.
Holding a database transaction open across that external call would be its own anti-pattern.
For that case, register with `handle_without_uow: Callable[[EventT], None]` instead of
`handle` — the dispatcher branches on which field is set and does **not** auto-wrap
`handle_without_uow`; the handler does its external call first, then opens
`with uow.transaction(idempotency_key=event.idempotence_key()):` itself around just the
write, exactly as `bold` does today. This is the one place this standard asks an author to
remember the wrapping by hand — narrowly scoped to "I need I/O before I can write," not the
default.

One thing neither `bold` nor `sona` implements, worth adding at the CDK/infra level on top
of this handler shape: **SQS partial-batch-failure reporting**
(`FunctionResponseTypes: [ReportBatchItemFailures]`), so a re-raise on one bad record doesn't
redeliver the whole batch. Safe without it (every handler is idempotent), just wasteful.

### §9.5 Cron (`entrypoints/cron/`)

EventBridge-scheduled. Housekeeping only — see `golden-path-and-migrations.md` for the one
load-bearing exception (expiring refresh tokens / stale pending orders).

---

## §10. Orchestration

Three tiers. Walk this decision tree in order for every new use case:

```
Does the use case mutate exactly one aggregate instance?
├── YES → §10.1: call the SUBCONTEXT'S OWN services/ function directly. No orchestrator.
└── NO → does it need a fact from outside this bounded context?
    ├── YES, synchronously, from an EXTERNAL system → §10.2a: domain port + adapter.
    ├── YES, synchronously, from ANOTHER BOUNDED CONTEXT → §10.2b: internal HTTP port,
    │   used ONLY to snapshot owned data (§9.2 above).
    └── does it mutate multiple aggregates?
        ├── Same product → §10.2: product-level orchestrator, calling SERVICES functions,
        │   composed into ONE atomic transaction via nested uow.transaction() (§8, see
        │   persistence-and-concurrency.md).
        └── Different products → §10.3: top-level orchestrator OR async event reaction —
            consistency is eventual, no shared transaction, ever.
```

### §10.1 Single aggregate — no orchestrator

Call the subcontext's own service function (`domain-and-application.md` §6) from the
entrypoint directly. Resist the urge to wrap a single-aggregate call in an "orchestrator" for
symmetry — see the Middle Man smell in `anti-patterns-and-design-principles.md`.

### §10.2 Same product, multiple aggregates — product-level orchestrator

**The orchestrator calls other subcontexts' `services/` functions. It never calls
`uow.repo(...)` or an aggregate method itself.** This is not a style choice — it is exactly
how `bold`'s real orchestrators are written, verified directly against
`apply_and_confirm_or_reject_breb_cashin_orchestrator.py`: it imports
`breb_cashin_management` (the service module) and calls other orchestrator/service
functions — never touches `uow.repo(...)` or an aggregate directly itself. `bold`'s own
`CLAUDE.md` states the layer order explicitly: `entrypoints → services → domain.model`; an
orchestrator is a `services/` module, and it respects that same order with respect to every
OTHER subcontext it coordinates.

```python
# commerce/services/confirm_order_orchestrator.py
from commons.adapters import logs, unit_of_work

from commerce.orders.domain.model import ports as order_ports
from commerce.orders.domain.model import value_objects as order_value_objects
# ^ typing only — the contract-6 exception (enforcement-and-style.md §16) now covers
#   value_objects AND ports: a value object for a plain pass-through param, a port ABC for a
#   caller-supplied adapter this function never constructs itself — never
#   aggregate/events/rules/adapters.
from commerce.orders.services import dto, orders
from commerce.stock.services import stock

_LOGGER = logs.get_logger()


def confirm_order(
    *, uow: unit_of_work.UnitOfWork, order_id: order_value_objects.OrderId,
    user_profile_port: order_ports.UserProfilePort,
) -> dto.OrderOutputDTO:
    # The profile fetch happens BEFORE with uow.transaction() opens —
    # persistence-and-concurrency.md §8's no-I/O-inside-an-open-transaction rule. A nested
    # uow.transaction() call joins the outer one as a no-op, so calling the port from inside
    # orders.confirm_order itself wouldn't help: THIS function's own transaction is what
    # actually holds the connection open.
    order = orders.get_order(uow=uow, order_id=order_id)
    profile = user_profile_port.get_profile(order_value_objects.CustomerId(value=order.customer_id))

    with uow.transaction():
        for line in order.lines:
            stock.reserve_stock(uow=uow, sku=line.sku, quantity=line.quantity)
        return orders.confirm_order(
            uow=uow, order_id=order_id,
            shipping_name=profile.full_name, shipping_email=profile.email,
        )
```

`orders.get_order`, `stock.reserve_stock`, and `orders.confirm_order` are ordinary
application-service functions (`domain-and-application.md` §6), each opening its **own**
`with uow.transaction():` internally — which, once inside the outer transaction above,
simply joins it (`persistence-and-concurrency.md` §8). If `stock.reserve_stock` raises
`InsufficientStockError` for any line, the whole mutation rolls back atomically: `Order` is
never left half-confirmed, no `Stock` is left partially decremented. The orchestrator never
sees `Stock` or `Order` as domain objects at all — only their services' DTOs and exceptions.
`orders.confirm_order` itself takes plain `shipping_name`/`shipping_email`, not the port —
see `persistence-and-concurrency.md` §8 for why the fetch had to move up to here.
`user_profile_port` is never constructed here either — the entrypoint (§9.1 above) builds
the concrete adapter and passes it in; this function only knows the port's abstract shape.

**(10.2a) External synchronous port** — the golden path's concrete case: `Order` needing the
current price for a SKU to snapshot onto each `OrderLine`. Defined in
`orders/domain/model/ports.py` as `PricingPort`, implemented in
`orders/adapters/pricing_adapter.py`, injected into the application service as a **required**
keyword argument (never `port: PricingPort | None = None` with an `or DefaultAdapter()`
fallback — §9.1 above) — never called from the aggregate itself. Modeled on `bold`'s
`BreBCashinPricingAdapter`, which plays the identical role: an external price lookup, called
from application code, with the result handed to the aggregate as a plain parameter. The
adapter itself retries transient failures with `backoff.on_exception` and parses the
response into a typed Pydantic DTO before it touches domain code — see
`persistence-and-concurrency.md`'s dependency table for the exact configuration, verified
against bold's real `bancolombia_cardless_cashout/adapter.py`.

**(10.2b) Internal synchronous port** — see §9.2 above. Same shape (required kwarg,
`backoff`, typed response DTO), but the adapter calls another product's
`entrypoints/web/internal.py` over HTTP instead of a third party, and — because the golden
path's only caller is a product-level orchestrator, not a single-aggregate service — it's the
**orchestrator**, not `orders.confirm_order`, that receives `UserProfilePort` and calls it,
before opening its own transaction (see the worked example above).

### §10.3 Cross-product — top-level orchestrator, eventual consistency

**This tier needs a genuine reason two products' services must be called synchronously in
one request, each committing independently** — not merely "this use case touches two
products." Most cross-product relationships are better served by §9.4's event consumer
than by a synchronous orchestrator: reach for `orchestrators/` only when the caller
genuinely needs *both* results back in the same response.

**This golden path's own cross-product relationship is the counter-example, not an
instance of this tier.** A deactivated `identity.users.User` should stop that customer's
pending `commerce.orders.Order`s. An earlier draft of this template had
`orchestrators/deactivate_user_cascade.py`: one function, unconditionally forwarding to
`auth.deactivate_user`. Read literally, it never orchestrated anything cross-product at
all — the whole "cascade" happens outside it, via §9.4's event consumer — and it forwarded
to exactly one service function unconditionally: the **Middle Man**
(`anti-patterns-and-design-principles.md` §22.2) says to delete. It took asking "why is
this an orchestrator if it only calls one aggregate?" to catch that the flagship example
for this section was violating this standard's own rule. Fixed: the function is gone,
`entrypoints/web/public.py`'s `deactivate_me` route calls `auth.deactivate_user` directly
(§10.1 — single-aggregate use case, full stop), and the explanation for why commerce's
reaction is event-driven, not a second call, now lives on `auth.deactivate_user` itself.

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
unit and one database).

**No compensation/saga machinery.** A guaranteed step 2 goes through the outbox + idempotent
consumer, not a retry loop in the orchestrator.

### §10.4 A deliberate divergence from the book: Order + Stock

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
