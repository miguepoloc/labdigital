# Architecture enforcement and style guide

> Topic excerpt of `../../../ARCHITECTURE.md` §2.1, §16–§17. If this file and
> `ARCHITECTURE.md` disagree, `ARCHITECTURE.md` wins.

## §2.1 `# type: ignore` discipline

`mypy.ini` sets `plugins = pydantic.mypy` and, load-bearing here, **`warn_unused_ignores =
True`** — a `# type: ignore` that stops being necessary becomes a build failure, not stale
code left lying around. The discipline itself: **a `# type: ignore` is a last resort, tried
only after the actual type is fixed and still doesn't check.** Four ignores that looked
unavoidable in this codebase's own history turned out fixable once actually looked at:

- `sns_client: object` → `mypy_boto3_sns.client.SNSClient` (the stub `boto3-stubs[sns]`
  already provides) — `object` was an untyped escape hatch, not a considered choice.
- `_REPO_REGISTRY: dict[..., type[Repository[Any]]]` → `dict[..., Callable[[Session],
  Repository[Any]]]` — the ABC declares no `__init__`, so `type[Repository[Any]]` couldn't
  express "callable with a session"; a `Callable` type states the real contract directly.
- A `Protocol` describing only `__tablename__` on an ORM row, `row.id` access flagged →
  adding `id: str` (accurate — every `HumanFriendlyId`-keyed row has one) was enough.
  SQLAlchemy 2.0's `Mapped[str]` satisfies a plain `id: str` structurally, no extra plugin.
- `EventConsumer.handle: Callable[[UoW, EventT], None] | Callable[[EventT], None]`,
  dispatched by inspecting a handler's parameter count at runtime — mypy genuinely cannot
  narrow a union of different-arity callables from a runtime check, so this **was** a real
  design problem. Fixed by splitting into two mutually-exclusive fields
  (`handle`/`handle_without_uow`, `entrypoints-and-orchestration.md` §9.4), each one
  concrete callable type — an improvement independent of mypy, since the call site now
  states its intent instead of the dispatcher inferring it from argument count.

**One ignore remains, and stays**: `@pydantic.computed_field  # type: ignore[prop-decorator]`
on `DomainEvent.event_type`. Verified directly: mypy raises `Decorators on top of @property
are not supported` for `@computed_field` stacked on `@property` even with the pydantic
plugin active and even with `@computed_field()` parens — pydantic's own documented mypy
limitation, not something a local type fix resolves. That's the actual test before writing
any `# type: ignore`: has the real type been tried and still doesn't check, or was it never
actually attempted?

## §16. Architecture enforcement — import-linter contracts

Both real Postgres-backed codebases studied enforce these with `import-linter` in CI, not by
convention. Applied **uniformly** to every product/subcontext — `sona-sso-backend` only
covered 2 of 4 contexts with the layering contract; don't repeat that gap, template contract
generation for every new subcontext:

1. **Domain purity**: nothing under `domain/` may import `fastapi`, `sqlalchemy`, `boto3`,
   or `httpx`.
2. **Layering, within a subcontext**: `services` may import `adapters` and `domain`;
   `adapters` may import `domain` but not `services`; `domain` imports neither.
3. **Context independence**: no subcontext imports another subcontext's `domain` or
   `services` directly — only via a product's local `commons/` (see
   `shared-kernel-and-testing.md`), a synchronous port, or an event.
4. **Commons independence**: `commons` (global or product-local) imports no product/subcontext.
5. **Entrypoint thinness**: `entrypoints/` may import `services` and `commons`, never its
   own product's `domain.model.aggregate`/`adapters` directly. **Two deliberate exceptions:**
   - A different product's `domain.model.events`: an event-consumer entrypoint (§9.4) needs
     the producing product's `IntegrationEvent` class to deserialize against — that's exactly
     what promoting a `DomainEvent` to `IntegrationEvent` is *for*, it's the public contract
     a consumer is meant to import.
   - **A subcontext's own port-implementing adapter module** (`orders/adapters/pricing_adapter.py`,
     `orders/adapters/user_profile_adapter.py`) — the entrypoint is the composition root
     (`entrypoints-and-orchestration.md` §9.1): it constructs the concrete adapter and
     threads it into a service/orchestrator call as a required keyword argument, exactly
     what bold's own `entrypoints/web/breb/breb_credibanco.py` does. Narrower than "the whole
     `adapters` package": `adapters/repository.py` (and `.orm`) stay forbidden — persistence
     is the one thing an entrypoint may never reach past the service layer for; only the
     outbound-port adapters (external HTTP clients) are allowed through, and only for
     construction, never for calling `uow.repo(...)`-equivalent methods directly.

   `aggregate` from either the same or a different product stays forbidden either way; only
   the event contract and the port-adapter *construction* cross.
6. **Orchestrator thinness**: a product-level `services/*_orchestrator.py` file, and
   everything under top-level `orchestrators/`, may import other subcontexts' `services`
   modules and `commons` — **never** any subcontext's `domain.model.aggregate`,
   `domain.model.events`, `domain.model.rules`, or `adapters`, and never calls
   `uow.repo(...)` or an aggregate command method directly. This is the rule that makes
   "orchestrators call services, never aggregates" enforceable by tooling instead of by code
   review vigilance alone (see `entrypoints-and-orchestration.md` §10.2).

   **Two narrow exceptions:**
   - `domain.model.value_objects` (found running this skill's own eval benchmark) — typed
     IDs and other value objects, **purely to type-hint a parameter it passes straight
     through** (e.g. `order_id: order_value_objects.OrderId`, aliased and imported for real
     in `confirm_order_orchestrator.py`, `entrypoints-and-orchestration.md` §10.2).
   - `domain.model.ports` (found building the template's `confirm_order_orchestrator.py`,
     `persistence-and-concurrency.md` §8 / `entrypoints-and-orchestration.md` §10.2b) — a
     port ABC (`UserProfilePort`), **purely to type-hint a caller-supplied adapter the
     orchestrator calls directly but never constructs**: the entrypoint builds the concrete
     adapter and passes it in; the orchestrator only ever sees the abstract port type. Not
     the same as importing `adapters` (still forbidden) — a port is a domain-declared
     abstraction, not the concrete I/O implementation.

   The rule exists to stop bypassing the service layer's business logic, not to forbid
   naming a type from another subcontext — neither a value object nor a port ABC carries an
   invariant an orchestrator could violate just by referencing it in a signature, since all
   actual persistence work still goes through the owning subcontext's own service function,
   and all actual I/O goes through a port instance the orchestrator received, not one it
   built. The line stays sharp: `value_objects` and `ports` for typing/pass-through, never
   `aggregate`/`events`/`rules`/`adapters` for anything.

If you write a new subcontext, it gets all 6 contracts, not a subset picked for "the ones
that seem relevant."

### A real `import-linter` gotcha, found by actually running it against the template

`import-linter`'s `forbidden` contract type checks the import graph **transitively by
default** — it doesn't understand "layer L may reach M only through gatekeeper N," it just
asks "is there *any* path from L to M, direct or indirect?" Since `services/orders.py`
legitimately imports `adapters/repository.py`, a naive contract 5 or 6 flags
`entrypoints -> services -> adapters` as a violation even though the entrypoint never
touches `adapters` itself. Both contracts need `allow_indirect_imports = true` — that makes
the contract check only *direct* imports from the source, which is what "don't reach past
the gatekeeper" actually means. Contract 3 (context independence) has the mirror-image
trap: list the two subcontexts' `domain`/`services` sub-modules individually and
`orders.services` importing `orders.domain` (fine — same subcontext) gets flagged as if it
were cross-context, because `independence` treats every listed module as its own sibling.
List the two subcontext *packages themselves*, not their internal sub-modules, so
everything inside one package is one sibling group. The template's own `.importlinter`
file has both fixes applied — copy the shape from there.

---

## §17. Style guide addendum (Google Python Style Guide specifics)

The full guide applies (https://google.github.io/styleguide/pyguide.html). The points below
are the ones most load-bearing in this codebase, cross-checked against real source in `bold`
and `sona-sso-backend` — not assumed.

### §17.1 Import modules, not names — verified, not optional

Google's guide states it plainly: *imports are for packages and modules only, not for
individual classes or functions.* This is not a minor stylistic footnote — it is applied
throughout every file this standard produces.

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
`commons/domain/aggregates.py` (`domain-and-application.md` §5.1), which imports `events` as
`domain_events` because the file's own methods use `events`/`event` as parameter names.

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

### §17.2 Logging — one shared logger, not `logging.getLogger(__name__)` per file

Do **not** write `_LOGGER = logging.getLogger(__name__)` in every file — that's the default
Python idiom, but it is not what either real codebase does. Instead, one cached, structured
logger, defined once:

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

This is `sona-sso-backend`'s real `commons/logs.py`, verified directly, adopted as-is — one
cached logger keyed by the Lambda function name, JSON-formatted, request-ID-aware via a
`contextvars.ContextVar` set by request middleware. `bold`'s equivalent is
`logs.get_lambda_logger()` — same shape, different name; this standard uses `get_logger()`.

Lazy `%s` formatting always in log calls (`_LOGGER.info("Order [%s] confirmed", order.id)`),
never an f-string in a logging call (it formats even when the level would suppress the
line). Exception *messages*, by contrast, do use f-strings with values in square brackets —
this split is `bold`'s consistent house style, adopted as-is.

### §17.3 Everything else

- **Docstrings**: mandatory on public API surfaces — aggregate factory/command methods,
  application-service functions, port abstract methods, `UnitOfWork` methods. Not required
  on small private helpers (`_to_orm`, `_order_repo`) — `bold`'s own deliberate line.
- **Type annotations**: on every function signature, public or private. `X | None`, never a
  bare `None` default without the union.
- **Reconstructing a value object from a plain scalar** (a path param, a DTO's `str` field):
  direct keyword construction — `OrderId(value=order_id)`, `CustomerId(value=order.customer_id)`
  (both `HumanFriendlyId`-backed — a plain str-to-str copy, no conversion) — never
  `OrderId.model_validate({"value": order_id})`. `model_validate` is for an
  already-dict-/JSON-shaped payload with more than one field; wrapping a single already-known
  scalar in a dict just to hand it to `model_validate` is indirection with no payoff —
  verified against bold's real entrypoints (`DepositId(value=deposit_id)`), which construct
  directly.
- **Email format validation: `pydantic.EmailStr`, never a hand-rolled regex** — verified as
  real, widespread bold precedent (`pydantic.EmailStr` on over a dozen real DTOs/models,
  never a custom pattern). `identity.users.value_objects.Email` wraps it in a
  `field_validator` rather than using `EmailStr` as the field type directly, because `Email`
  is a domain `ValueObject` built deep inside `User.register()`, not a request-body field
  FastAPI parses at the boundary — a bare `EmailStr` field would raise
  `pydantic.ValidationError` on failure, a type `commons.adapters.api.exception_handler`
  (§16) doesn't map, surfacing as an unhandled 500 instead of the established 422:

  ```python
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
- **Naming**: `snake_case` functions/modules, `PascalCase` classes, `_leading_underscore`
  for module-private helpers, `CAPS_WITH_UNDER` constants. Exception classes end in `Error`.
- **No mutable default arguments. No bare `except:`. No `staticmethod`** — a module-level
  function instead.
- **`...` vs. `pass` for an empty body**: the test is "is this a contract someone else must
  implement, or is this already a complete, working thing?"
  - **`...`** — an abstract method (`BusinessRule`, `Repository[T]`), a `Protocol` method,
    any signature whose real implementation belongs elsewhere. Convention borrowed from
    `.pyi` type-stub files, where `...` specifically signals "contract, not logic."
  - **`pass`** — a concrete class that is finished as written: a typed-ID marker
    (`StockId(UuidV7Id): pass`), a framework base with nothing to add
    (`Base(DeclarativeBase): pass`), or a marker exception subclass
    (`NotFoundError(DomainError): pass`) — `raise NotFoundError(...)` works today, there is
    nothing left to fill in.
  - **Neither** — if the class or function already has a docstring, the docstring itself is
    the body; Python doesn't need (and this standard doesn't add) a redundant `pass`/`...`
    after it (`IntegrationEvent`).

  Using `pass` on an abstract method reads as "this method does nothing" when it actually
  means "implement this"; using `...` on a finished concrete class reads as an unfinished
  stub when nothing is missing. Get this backwards and a reader — human or AI — draws the
  wrong conclusion about whether there's work left to do.
- **`enum.StrEnum` (3.11+), not `class X(str, enum.Enum):`**. The old mixin form's `str()`
  returns `"ClassName.MEMBER"` instead of the raw value unless every consuming class
  remembers to override `__str__`; `StrEnum` gets this right natively. `bold`'s own
  `Currencies` still uses the old mixin form — not a reason to copy it here: this standard
  targets Python 3.13, where `StrEnum` has been available for three releases.
- **`enum.auto()`, never a value retyped by hand, for any `StrEnum` whose values are its own
  member names** — lowercase or uppercase, both are covered. `StrEnum` overrides
  `_generate_next_value_` to produce the lowercased member name, so `PENDING = enum.auto()`
  on a plain `enum.StrEnum` already gives `.value == "pending"`. For the uppercase case
  (ISO-4217 currency codes, unit codes — anywhere lowercasing would silently produce the
  wrong value), `commons/domain/enums.py` defines `UpperStrEnum(enum.StrEnum)`:

  ```python
  class UpperStrEnum(enum.StrEnum):
      @staticmethod
      def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str:
          return name


  class Currencies(enums.UpperStrEnum):
      COP = enum.auto()   # .value == "COP"
      USD = enum.auto()
  ```

  Neither base is "more correct" — pick by what the value actually needs to be, and never
  type the string out by hand for either case.
- **`dataclasses.dataclass(frozen=True)` vs. a `ValueObject`/Pydantic model**: a Pydantic
  model exists to validate and (de)serialize data that crosses a real boundary — parsed from
  JSON, persisted, sent over HTTP. A plain frozen `dataclass` is for an immutable,
  in-process-only structure built directly in Python code that never crosses such a
  boundary — `EventConsumer` (`entrypoints-and-orchestration.md` §9.4), pairing an event
  class with a handler function, is exactly that: neither a `type` nor a `Callable` is
  something Pydantic validates against external input in the first place, so reaching for
  `ValueObject` there would add validation machinery with nothing for it to validate.

  **A port's return type is the opposite case, not a look-alike of `EventConsumer`.** Data a
  port returns (`UserProfilePort.get_profile`'s `UserProfile`, `entrypoints-and-orchestration.md`
  §10.2b) *did* cross a boundary — the adapter parsed it out of an HTTP response one hop
  earlier — it just doesn't re-validate it itself. Verified against bold's real
  `AuthResponseBody` (assembled from an already-parsed auth response, handed to application
  code the same way): `base_types.ValueObject`, Pydantic, not a dataclass — and so is every
  shape in bold's real `output_dtos.py`. The dividing line is whether the data was ever
  assembled from parsed external input, not whether this specific line calls
  `.model_validate()` again.
- **Formatting**: delegate entirely to `ruff format`; configure `ruff.toml` once, stop
  thinking about line length.
