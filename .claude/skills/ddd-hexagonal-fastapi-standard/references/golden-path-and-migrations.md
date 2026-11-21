# Golden-path reference example and migrations

> Topic excerpt of `../../../ARCHITECTURE.md` §18–§19. If this file and `ARCHITECTURE.md`
> disagree, `ARCHITECTURE.md` wins.

## §18. Migrations (Alembic)

- Single `migrations/` directory, one physical database, `target_metadata =
  orm_base.Base.metadata` — one shared metadata object, many logical bounded contexts
  (`sona`'s deliberate choice, fine for a single-database deployment).
- **Autogenerate only.** Every migration keeps Alembic's default
  `<12-hex-revision>_<slug>.py` naming. `sona` has hand-named exceptions from bypassing this
  under deadline pressure — the cautionary example, not a precedent. A genuine hand-authored
  data migration still goes through `alembic revision` (scaffolded, then hand-filled), never
  a loose script.
- Cron jobs (`entrypoints-and-orchestration.md` §9.5) are housekeeping, not migrations, and
  don't touch this directory. The one load-bearing exception: `identity/entrypoints/cron/
  expire_refresh_tokens.py` and `commerce/entrypoints/cron/expire_pending_orders.py` are
  genuinely part of the golden path's correctness story (§9.3's "no synchronous existence
  check" relies on refresh tokens actually expiring), not optional housekeeping — still not
  a migration, but don't assume every cron job is purely cosmetic either.

---

## §19. The golden-path reference example

The template project (`template/` in the repo root) implements this standard end-to-end:

- **`identity/users/`** — registration, login, RS256 JWT issuance, refresh-token
  storage/revocation in Postgres. Emits `UserRegistered`, `UserDeactivated`
  (`IntegrationEvent`).
- **`commerce/orders/`** + **`commerce/stock/`** — `Order` (with `OrderLine` as a value
  object, matching the book — not a separate aggregate; each `OrderLine` carries a
  `unit_price: money.PositiveMoney` snapshotted at order-creation time), `Stock`
  (deliberately separate, see `entrypoints-and-orchestration.md` §10.4, price-free —
  inventory quantity is its only concern). Demonstrates:
  - single-aggregate use case (§10.1);
  - same-product multi-aggregate orchestration calling services only (§10.2);
  - external synchronous port (§10.2a, doing real work — fetching the current unit price
    for a SKU);
  - internal synchronous port (§10.2b);
  - cross-product **eventual-consistency** reaction via the shared
    `commons.adapters.sqs.process_sqs_event` dispatcher, idempotent (§9.4/§12.2) — this
    golden path's one cross-product relationship turned out to be exactly this, not §10.3's
    synchronous top-level-orchestrator tier (`entrypoints-and-orchestration.md` §10.3
    explains why);
  - a cron entrypoint (§9.5/§18);
  - `Order.total` as a derived `@property`, never a stored field.
- **`commerce/commons/`** — `Sku`, shared between `orders` and `stock`.
- **`commons/domain/money.py`** — `Money`/`NonNegativeMoney`/`PositiveMoney`, ported from
  `bold`, used wherever the template needs an amount of currency.

Every code sample across the other reference files in this skill is drawn from, and kept in
sync with, this template — if they disagree, the template is the bug.

**When asked to "show a complete working example" of any pattern in this standard**, this is
the example to point to (or build, if `template/` doesn't exist yet in the repo you're
working in) — don't invent a different domain (a blog, a to-do list) unless the user
explicitly asks for one; `Order`/`Stock`/`User` already demonstrates every layer and every
cross-cutting concern this standard defines, and reusing it keeps terminology consistent
across the whole codebase.
