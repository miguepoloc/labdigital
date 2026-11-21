# Golden-path template

The reference implementation of `../ARCHITECTURE.md` and `../.claude/skills/
ddd-hexagonal-fastapi-standard/`. Every code sample in those two documents is drawn from,
and kept in sync with, this project — if they disagree, this code is the bug (ARCHITECTURE.md
§19).

## What's here

- **`identity/users/`** — registration, login, RS256 JWT issuance, refresh-token
  storage/revocation. Emits `UserRegistered` (internal), `UserDeactivated`
  (`IntegrationEvent`).
- **`commerce/orders/`** + **`commerce/stock/`** — `Order` (with `OrderLine` as a value
  object, matching Cosmic Python's own `Product`/`Batch` chapter — not a separate
  aggregate) and `Stock` (deliberately kept separate, ARCHITECTURE.md §10.4). Demonstrates
  §10.1 (single-aggregate, `orders.create_order`) and §10.2 (product-level orchestrator,
  `confirm_order_orchestrator`/`cancel_order_orchestrator`), both port kinds (§10.2a/b), the
  outbox (§11), and optimistic concurrency (§8.1).
- **`commons/`** — the shared kernel: base `Entity`/`AggregateRoot`/`ValueObject`, `Money`,
  the generic `UnitOfWork`, the outbox, the SQS event-consumer dispatcher, RS256
  auth, structured logging.
- **`orchestrators/`** — empty except `__init__.py`, deliberately: §10.3 (a genuine top-level
  cross-product orchestrator) needs a case where two products' services must be called
  synchronously in the same request, each committing independently. This golden path's one
  cross-product relationship (`identity.users` deactivation → `commerce.orders` cancelling
  pending orders) turned out not to be that case — it's a straight §10.1 single-aggregate use
  case in `identity`, reacting asynchronously in `commerce` via the outbox-published
  `UserDeactivated` event (§9.4/§11), not a second synchronous call. An earlier draft of this
  template had a `deactivate_user_cascade` here that unconditionally forwarded to
  `auth.deactivate_user` — a Middle Man (§22.2), not real orchestration; deleted once traced
  through, not kept just to have "an example" of the tier. The directory stays as the real
  extension point for whenever a genuine case shows up.

## Running it locally

```bash
cp .env.example .env   # then fill in a real RS256 key pair, see the comment in the file
make install
make hooks               # installs pre-commit + commit-msg git hooks, see CONTRIBUTING.md
make dev-up             # starts Postgres via docker-compose
make migration m="initial schema"   # autogenerate — never hand-write a migration (§18)
make migrate
make check               # lint + typecheck + import-linter contracts + unit tests
```

See `CONTRIBUTING.md` for branch naming, commit message format, and what CI
(`.github/workflows/ci.yml`) re-checks on every PR.

There's no `main.py` — every `entrypoints/web/*.py` file is its own FastAPI app +
`mangum.Mangum(app)` handler, meant to run as a separate Lambda in production
(ARCHITECTURE.md §9.1). For local development, run any one of them directly with uvicorn,
e.g.:

```bash
uv run uvicorn backend.identity.entrypoints.web.public:app --reload --port 8000
uv run uvicorn backend.identity.entrypoints.web.internal:app --reload --port 8001
uv run uvicorn backend.commerce.entrypoints.web.orders:app --reload --port 8002
uv run uvicorn backend.commerce.entrypoints.web.stock:app --reload --port 8003
```

`orders.py` and `stock.py` are two separate files/Lambdas, not one shared router — orders and
stock are independent bounded contexts (§10.4) with independent deploy lifecycles, so they
never share a router file (verified against sona-sso-backend's own
`organizations.py`/`sso_connections.py` split, ARCHITECTURE.md §16.1).

## Tests

```bash
make test-unit    # fakes, no I/O, milliseconds (ARCHITECTURE.md §15)
make test         # everything, including integration tests that need Postgres (make dev-up first)
```

Tests live in one top-level `tests/` tree, **outside** `src/` — never nested inside a
subcontext under `src/backend/`. `src/backend/` is what `hatch build` packages into the
wheel (`[tool.hatch.build.targets.wheel] packages = ["src/backend"]`); test code nested
inside it would ship in the production artifact. Verified against `sona-sso-backend`'s real
`backend/tests/unit/backend/sona_sso/...` — a single tree mirroring the package path, kept
as a sibling of the package, not a child of it.

```
tests/
├── unit/backend/<same path as src/backend/...>/       # fakes.py + test_*.py, no I/O
├── integration/backend/<same path>/                    # real Postgres via testcontainers
└── e2e/                                                 # FastAPI TestClient, full round trip
```

Each subcontext's `fakes.py` (implementing that subcontext's `Repository[T]` in memory)
lives next to its `test_*.py` under `tests/unit/backend/...` — e.g.
`tests/unit/backend/commerce/stock/fakes.py`. Integration tests go in the mirrored
`tests/integration/backend/...` path, exercising real `Repository`/`UnitOfWork`/
`version_id_col` behavior against Postgres via testcontainers.

**Current status**: this reshuffle moved the tree into the right shape but the actual test
bodies (`fakes.py`, `test_orders.py`, `test_stock.py`, `test_auth.py`,
`commerce/stock`'s `test_repository.py`) were lost in the move and still need to be
rewritten — see `shared-kernel-and-testing.md`'s `FakeStockRepository` sample for the shape
to follow.

## Deliberate simplifications, called out so they don't look like oversights

- `OrderLine` is stored as JSONB on the `orders` row rather than a child table — no query
  needs to reach into individual lines yet (§22.2's Middle Man caution: don't build
  structure you don't have a use for).
- The outbox relay (`*/entrypoints/cron/outbox_relay.py`) publishes directly via `boto3`
  rather than through a queue of its own — fine at this scale; if relay throughput ever
  becomes a bottleneck, that's a real, separate problem to solve later, not one to
  pre-solve here.
- `PRICING_SERVICE_BASE_URL` points at a hypothetical external pricing service that doesn't
  exist in this template — `commerce.orders.adapters.pricing_adapter.HttpPricingAdapter` is
  real, working HTTP-client code, but you'll need to point it at something that actually
  implements `GET /prices/{sku}` (or inject a different `PricingPort` implementation) to
  run `create_order` end-to-end outside of tests.
