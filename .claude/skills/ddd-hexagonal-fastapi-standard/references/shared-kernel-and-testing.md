# Shared kernel and testing strategy

> Topic excerpt of `../../../ARCHITECTURE.md` §3.2, §14–§15. If this file and
> `ARCHITECTURE.md` disagree, `ARCHITECTURE.md` wins.

## Two tiers of shared code — don't confuse them

### Global `commons/` (§14)

Import-linter enforces: `commons` never imports from any product.

```
commons/
├── domain/{base_model,entities,aggregates,value_objects,enums,money,events,business_rules,
│           exceptions,repositories,audit}.py  # money.py: Money — see domain-and-application.md;
│                                              # enums.py: UpperStrEnum — see enforcement-and-style.md;
│                                              # audit.py: AuditEntry — see below
├── application/dto.py
└── adapters/
    ├── settings.py           # Settings(pydantic_settings.BaseSettings), get_settings() —
    │                        # see below; every env var this codebase reads, one vocabulary
    ├── engine.py            # sync session factory, NullPool outside local dev
    ├── orm_base.py           # Base, TimestampsMixin, IdempotencyKeyOrm (shared, §12.1+§12.2),
    │                        # OutboxEventOrm, AuditLogOrm
    ├── unit_of_work.py        # UnitOfWork, register_repo; uow.audit — see below
    ├── repository_helpers.py   # insert_with_id_retry
    ├── outbox.py               # OutboxRepository, relay helper
    ├── audit.py                # AuditRepository — see below
    ├── sqs.py                    # EventConsumer, process_sqs_event()
    ├── authentication.py          # RS256 jwt_validator + issuer
    ├── logs.py                    # get_logger()
    └── api/
        ├── exception_handler.py  # status_for()
        └── middleware.py          # request logging
```

### Audit log: who did what, without a growing central file

A shared vocabulary in `commons/`, same placement as `outbox` (no dedicated bounded context,
no `services/` layer — `AuditRepository` is a concrete class, not an ABC a domain test
fakes), same shape as `sona-sso-backend`'s real `audit` context (Postgres table, repository,
same-transaction write, a `changes` diff) — but keyed on the aggregate
(`AuditRepository.list_for_aggregate(aggregate_type, aggregate_id, ...)`), not a tenancy
anchor (`list_for_org`) this standard's multi-product domain doesn't have; `sona-sso-backend`'s
own `console_auth` login/logout rows, written with `org_id=None`, are permanently unreachable
through its org-only API — the gap this fixes.

`aggregate_type`/`aggregate_id`/`action` are plain `str` in `commons/`, never typed value
objects or a shared enum: `commons/` cannot import any product (contract 4), and each
product declares its own local `AuditAction`/`AuditAggregateType` enum instead — growth
happens in the product that grew, never in `commons/`. Named `aggregate_type`/`aggregate_id`,
not `entity_type`/`entity_id`: this codebase already distinguishes `Entity[IdT]` from
`AggregateRoot[IdT]`, and every audit-writing call site is where `uow.repo(...).add`/
`.update` does its work. `AuditLogOrm.id` uses `sa.Identity()` (a real Postgres sequence),
not `HumanFriendlyId`: an unbounded append-only log is exactly the case a random-10-character
scheme isn't sized for.

`AuditEntry.actor` is one `Actor` value object (`id: str | None`, `label: str`), never two
loose `actor_id`/`actor_label` parameters threaded through every service signature — an
entrypoint builds it once from the verified JWT and passes it down, same as a `PricingPort`
instance, never from a request-body DTO (a client could claim to be anyone). A
system-initiated entry (a cron, an async event reaction) builds its own `Actor` with
`id=None` and a `"system:<what triggered it>"` label. Full worked example (the enums, the
entrypoint→orchestrator→service threading, the `uow.audit.add(...)` calls in both
`identity/users/services/auth.py` and `commerce/orders/services/orders.py`):
ARCHITECTURE.md §14.2.

**Exactly one global shared layer.** `sona`'s three coexisting generations
(`shared_package`→`sona_common`→`common`) is the failure mode this rule prevents (see
`anti-patterns-and-design-principles.md`): extend `commons/`, never fork it.

### Configuration: one settings vocabulary, `pydantic_settings.BaseSettings`

The same "one vocabulary" rule §13 applies to exceptions, applied to configuration: every
env var this codebase reads goes through one `Settings` field, never a scattered
`os.environ[...]` call wherever an adapter happens to need it:

```python
# commons/adapters/settings.py
class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_private_key_pem: str    # required, no default
    jwt_public_key_pem: str
    internal_api_key: str
    db_port: int = 5432          # real type coercion — a malformed value fails at
                                  # Settings() construction, not on first query
    # ... every other env var this codebase reads


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()   # cached module-level singleton — the same shape
    return _SETTINGS             # commons.adapters.engine's own _engine caching uses
```

Verified against `sona-sso-backend`'s real `commons/settings.py` — the directly comparable
precedent (same stack), not bold's heavier SSM-backed version. `pydantic-settings` is
already a declared dependency; reach for it, don't hand-roll `os.environ.get(...)` instead.

### Product-local `commons/` (§3.2)

`bold`'s real source contains not only the global `bold.commons` but also product-local
shared modules, e.g. `bold.deposit.breb.commons` — a shared-vocabulary layer for concepts
used by several subcontexts of the **same** product, but not general enough for the global
`commons/`.

This standard adopts the same middle tier: `<product>/commons/`. Rule: a value object or
type used by two or more subcontexts of one product (e.g. `Sku`, needed by both
`commerce/orders` and `commerce/stock`) lives in `<product>/commons/`, **not** duplicated in
each subcontext, and **not** promoted to the global `commons/` unless a *second product*
also needs it. This also closes a real hole in import-linter contract 3
(`enforcement-and-style.md`): a subcontext importing a sibling subcontext's `domain/`
directly is forbidden, but importing its own product's `commons/` is explicitly allowed.

**Deciding where a shared thing goes**: used by 2+ subcontexts of one product → that
product's `commons/`. Used by 2+ *products* → the global `commons/`. Used by exactly one
subcontext → it doesn't belong in either, keep it local to that subcontext.

---

## §15. Testing strategy

| Layer | What | How | Speed |
|---|---|---|---|
| `domain/`, `services/` unit tests | Aggregate invariants, application-service orchestration logic | **Fakes**, not mocks — an in-memory `FakeRepository[T]` implementing `Repository[T]` (`sona`'s `fake_*_repository.py` convention). A fake exercises real service-layer code against real (if simplified) repository semantics; a mock only verifies calls happened. | Milliseconds |
| `adapters/` integration tests | ORM mapping round-trips, repository queries, UoW transaction/rollback behavior | Real PostgreSQL via **testcontainers** — never SQLite, never a mocked `Session`. SQLite's type/constraint behavior diverges from Postgres enough to hide real bugs (a `JSONB` column, a `unique` constraint interaction, `version_id_col` — none of these behave the same on SQLite). | Seconds |
| `entrypoints/` e2e tests | Full route → service → repository → DB round trip, one file per Lambda | FastAPI `TestClient` against the same app object `mangum.Mangum` wraps, real Postgres | Seconds |

`uow.outbox` and event publication are **no-op in `LOCAL`/`TEST`** environments (`sona`'s
pattern) so integration/e2e tests never need to mock SNS/SQS to stay hermetic; assert against
the `outbox_events` table's rows directly instead of against a mocked publish call.

**Where tests live**: one top-level `tests/` tree, never nested inside `src/backend/`.
`[tool.hatch.build.targets.wheel] packages = ["src/backend"]` packages everything under that
path into the production wheel — a subcontext's `tests/` living inside it ships test code in
the artifact. Verified against `sona-sso-backend`'s real `backend/tests/unit/backend/sona_sso/...`:
a single tree, sibling to the package, mirroring its full path underneath (`tests/unit/backend/...`,
`tests/integration/backend/...`, `tests/e2e/`). `pyproject.toml` needs `testpaths = ["tests"]`
and `pythonpath = ["src", "."]` — the `.` so `tests` itself resolves as an importable package.

**Writing a fake repository** — one per aggregate, living next to its `test_*.py` under
`tests/unit/backend/<same path as src/backend/...>/`:

```python
# tests/unit/backend/commerce/stock/fakes.py
from commons.domain import repositories

from commerce.stock.domain.model import aggregate, exceptions


class FakeStockRepository(repositories.Repository[aggregate.Stock]):
    def __init__(self) -> None:
        self._by_id: dict = {}

    def add(self, stock: aggregate.Stock) -> None:
        self._by_id[stock.id] = stock

    def update(self, stock: aggregate.Stock) -> None:
        self._by_id[stock.id] = stock

    def get_by_sku(self, sku: object) -> aggregate.Stock:
        for stock in self._by_id.values():
            if stock.sku == sku:
                return stock
        raise exceptions.StockNotFoundError(sku=sku)
```

(A real fake also mimics `add`/`update` draining and recording the entity's events to a
fake outbox, matching what `DefaultStockRepository` does internally — see
`persistence-and-concurrency.md` §7 and the template's own `tests/unit/fakes.py` for the
full shape, `_OutboxLike` Protocol included.)

Wire a `UnitOfWork` whose `repo()` returns fakes instead of real ones for domain/application
tests — this is what makes `services/stock.py`'s functions testable without a database at
all, in line with the "domain first, no I/O" step of the bounded-context recipe in
`../SKILL.md`.
