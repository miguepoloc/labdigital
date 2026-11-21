---
name: ddd-hexagonal-fastapi-standard
description: The canonical DDD + Hexagonal architecture standard for backend services built with FastAPI, PostgreSQL, and AWS Lambda — bounded contexts, aggregates, value objects, Unit of Work, orchestrators, domain events + transactional outbox, idempotency, optimistic concurrency, testing, import-linter contracts, and a Google-style-guide-aligned coding style, verified line-by-line against real production code (bold, sona, sona-sso-backend) rather than invented. Use this skill whenever the user asks to create a new bounded context or product, add an aggregate, value object, domain event, business rule, or exception; write a repository, ORM mapping, or port/adapter; add a FastAPI endpoint (public or internal), an SQS event consumer, or a cron job; implement or debug an orchestrator (same-product or cross-product); reason about transactions, the Unit of Work, race conditions, idempotency, or the outbox pattern; or ask any architectural question about how layers connect in a backend following this standard — even when the request doesn't say "DDD" or "hexagonal" explicitly, e.g. "add an endpoint to confirm an order", "create a new module for X", "why is this event never published", "how do I stop two requests from double-selling the same stock".
---

# DDD + Hexagonal Architecture Standard (FastAPI + PostgreSQL + Lambda)

This skill is the operating manual for building backend services in this standard. It does
not re-derive the architecture — that reasoning, and every real-code citation behind it, is
in [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md), the source of truth. This skill exists
to make that document *actionable*: a routing table telling you which part to read for the
task in front of you, plus the step-by-step recipes that document doesn't spell out as
recipes.

**If this skill and `ARCHITECTURE.md` ever disagree, `ARCHITECTURE.md` wins** — the
`references/` files here are topic-focused excerpts of it, kept in sync, not a second
source of truth.

## Before touching any code: read §1–4 of `ARCHITECTURE.md`

Every task in this standard depends on four things that are too foundational to summarize
away — read them directly, they're short:

- **§1 Guiding principles** — 11 rules, each with a one-line reason. The two that get
  violated most often when a task is rushed: §1.5 (orchestrators call services, never
  aggregates/repos directly) and §1.6 (a recorded domain event must have a documented drain
  point, or it must not be recorded).
- **§2 Tech stack** — Python 3.13, `uv`, FastAPI+Mangum on Lambda only (so SQLAlchemy is
  **sync**), PostgreSQL, Pydantic v2, `ruff`, `import-linter`, `pytest`+testcontainers.
- **§3 Repository layout** — the monorepo shape: `<product>/<subcontext>/` two levels deep,
  uniformly, even for a product with one subcontext today. §3.1's naming rule: a subcontext
  folder is named after the aggregate it contains (`stock/` → `Stock`), never a generic
  category. §3.2: a `<product>/commons/` tier for value objects shared by that product's own
  subcontexts (not the global `commons/`).
- **§4 Bounded context anatomy** — the exact file tree every subcontext has, what's REQUIRED
  vs. OPTIONAL in it, and the hard rule: nothing outside a subcontext's own `services/` may
  import that subcontext's `domain/` or `adapters/` — not an entrypoint, not an orchestrator.

## Routing table — which reference file for which task

| If the task involves... | Read |
|---|---|
| An aggregate, value object, typed ID, business rule, domain exception, domain event class, a port, or `Money` | [`references/domain-and-application.md`](references/domain-and-application.md) — also covers the `services/` application layer that calls those |
| A repository, ORM mapping (`orm.py`), or `_to_orm`/`_to_entity` mappers; the Unit of Work; a race condition / "two requests wrote at once" bug | [`references/persistence-and-concurrency.md`](references/persistence-and-concurrency.md) |
| A FastAPI route (`public.py`/`internal.py`), auth/JWT, an SQS event consumer, a cron job, or **any** multi-aggregate/cross-context coordination (an orchestrator) | [`references/entrypoints-and-orchestration.md`](references/entrypoints-and-orchestration.md) — **read the orchestration decision tree here before writing any function that touches more than one aggregate** |
| A domain event that needs to leave its bounded context, the outbox, `Idempotency-Key` handling, or the `DomainError` hierarchy / HTTP status mapping | [`references/events-idempotency-errors.md`](references/events-idempotency-errors.md) |
| What goes in `commons/` vs. a product-local `commons/`, or how to write a test (unit/integration/e2e) | [`references/shared-kernel-and-testing.md`](references/shared-kernel-and-testing.md) |
| An `import-linter` contract failure, or a style question (imports, logging, naming, `...` vs. `pass`, `StrEnum`, `dataclass` vs. Pydantic) | [`references/enforcement-and-style.md`](references/enforcement-and-style.md) |
| "Show me a working example" / Alembic migrations | [`references/golden-path-and-migrations.md`](references/golden-path-and-migrations.md) |
| "Is this an anti-pattern?" / a design-principle or code-smell question (Law of Demeter, Feature Envy, SOLID, ...) | [`references/anti-patterns-and-design-principles.md`](references/anti-patterns-and-design-principles.md) |
| A term you don't recognize, or "where did this rule come from" | [`references/glossary-and-sources.md`](references/glossary-and-sources.md) |

Read only what the task needs — these files are split by topic specifically so you don't
have to load all ~2,000 lines of `ARCHITECTURE.md` for a one-file change.

## Recipe: creating a new bounded context

This is the order that keeps every intermediate state importable and testable — matches
`sona-sso-backend`'s own documented recipe (`docs/ARCHITECTURE.md` §15) and `bold`'s
"Checklist: Adding New Event" habit of writing the steps down instead of relying on memory.

1. **Name it.** Pick the aggregate's name first (`Stock`, `Order`) — the subcontext folder
   is that name in `snake_case` (§3.1). If it's the first subcontext of a new product, pick
   the product name too (a capability, not an aggregate name — `commerce`, `identity`).
2. **Domain first, no I/O.** Write `domain/model/aggregate.py` (the aggregate root + factory
   + command methods), `value_objects.py` (its typed ID + local VOs), `exceptions.py` (one
   class per invalid transition), `events.py` if it raises any. This is pure Python — no
   `fastapi`, `sqlalchemy`, `boto3` import is even possible here (import-linter contract 1
   will fail the build if one sneaks in). → `references/domain-and-application.md`.
3. **Ports, if this aggregate needs one.** Only if it needs a synchronous external call or a
   snapshot from another bounded context (§5.6/§10.2) — most subcontexts don't need this
   step. → `references/domain-and-application.md`.
4. **Adapters.** `adapters/orm.py` (SQLAlchemy mapping, remember `version_id_col` for
   optimistic concurrency), `adapters/repository.py` (`_to_orm`/`_to_entity` + the concrete
   `Repository[T]`), register it with `unit_of_work.register_repo(...)`.
   → `references/persistence-and-concurrency.md`.
5. **Application service.** `services/<subcontext>.py` — one function per use case, the
   *only* place allowed to call `uow.repo(...)` or an aggregate method for this subcontext.
   `services/dto.py` for input/output DTOs. → `references/domain-and-application.md`.
6. **Entrypoint.** Add the route/event-consumer/cron job that calls the service function.
   Decide first whether this use case is single-aggregate (call the service directly, no
   orchestrator) or multi-aggregate (walk the decision tree in
   `references/entrypoints-and-orchestration.md` — **do this before writing an orchestrator
   you might not need**).
7. **Migration.** `alembic revision --autogenerate` — never hand-write the file, never skip
   this step even for a "just testing locally" table.
8. **Tests.** Unit tests against a fake repository for the domain/service logic, integration
   tests against real Postgres (testcontainers) for the repository/ORM mapping.
   → `references/shared-kernel-and-testing.md`.
9. **Import-linter contract.** New subcontext = same 6 contracts as every other one, not a
   subset (§16's own warning: `sona-sso-backend` skipped this for 2 of 4 contexts and it
   went unnoticed for a while). → `references/enforcement-and-style.md`.

If step 6 reveals the use case touches a **second aggregate**, stop and read the
orchestration decision tree before writing anything — it tells you in one pass whether you
need a product-level orchestrator (atomic, same product), a top-level orchestrator (eventual
consistency, cross-product), or neither.

## Non-negotiables, restated because they're the easiest to get wrong under time pressure

- An orchestrator that calls `uow.repo(...)` or an aggregate method directly is wrong,
  every time — it calls a `services/` function instead. This is enforced by import-linter
  contract 6, not just this sentence.
- A `record_event(...)` call with no corresponding `pull_events()` + outbox write in the same
  transaction is wrong, every time — it's dead code that looks alive
  (`sona-sso-backend` shipped exactly this).
- Every mutating event-consumer handler is idempotent, every time — SQS is at-least-once,
  no exceptions to plan around.
- `datetime` never appears in a domain field or an ORM column — `PosixTime` +
  `BigInteger`, always.
- Import a *module*, never a class or function directly, in every file you write for this
  standard (`from x import y`, then `y.Thing`) — this is checked in code review the same way
  a missing test would be.

When in doubt about any of these, the "why" — with the real code it was verified against —
is one `Ctrl+F` away in `ARCHITECTURE.md`.
