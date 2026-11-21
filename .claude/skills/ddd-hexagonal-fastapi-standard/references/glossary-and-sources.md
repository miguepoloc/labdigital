# Glossary and source material

> Topic excerpt of `../../../ARCHITECTURE.md` §21 and its Appendix. If this file and
> `ARCHITECTURE.md` disagree, `ARCHITECTURE.md` wins.

## §21. Glossary

| Term | Meaning here |
|---|---|
| **Product** | Top-level business capability grouping (`identity`, `commerce`). |
| **Subcontext** | A bounded context proper — owns exactly one aggregate concept, named after it. |
| **Aggregate** | A cluster of domain objects treated as one consistency boundary; only the root is referenced from outside. |
| **Value Object** | Immutable, defined by its value, no identity. |
| **Entity** | Has identity (`id`), mutable. |
| **Port** | An abstract interface declared by the domain for an outbound synchronous dependency. |
| **Adapter** | A concrete implementation of a port, or of the generic `Repository` contract. |
| **Domain event** | A fact recorded by an aggregate, internal to its bounded context unless promoted. |
| **Integration event** | A domain event's public, versioned representation, published via the outbox. |
| **Orchestrator** | A function coordinating multiple subcontexts' `services/` functions — product-level (atomic) or top-level (eventual consistency). Never touches `domain/`/`adapters/` directly. |
| **Outbox** | A table written in the same transaction as an aggregate mutation, later relayed to the message broker. |
| **UoW (Unit of Work)** | The transaction-boundary abstraction; one generic class, resolves repositories by aggregate type. |
| **PosixTime** | Integer-microseconds-since-epoch value object; the only timestamp representation used, domain or database. |
| **Optimistic concurrency** | Detecting a lost write-write race by version-checking at write time rather than locking at read time — `AggregateRoot.version` + SQLAlchemy's `version_id_col`, raising `ConcurrentModificationError`. |

## Where every rule in this standard came from

Every non-obvious rule in this standard cites a specific file in a specific real codebase —
not "best practice" asserted without a source. If you need to verify a claim, or explain to
someone why a rule exists, these are the files it was checked against:

- **`bold`**: `lambdas/bold/deposit/` (application code, incl. `breb/breb_cashin/` — the
  file-by-file source for aggregates, the application layer, and the orchestrator-calls-
  services rule; `breb/services/apply_and_confirm_or_reject_breb_cashin_orchestrator.py`
  specifically for that last one), `infra/bold/deposit/` (CDK), `lambdas/bold/commons/`
  (shared kernel — `base_types.py` for `Entity`/`AggregateEventAware` and non-generic ID
  typing, and `RootEntityVersion`/`RootEntity.version` for the optimistic-concurrency
  source; `commons/adapters/unit_of_work.py`'s `_add_write_operation`/
  `ConcurrentModificationError` for the same), `lambdas/bold/commons/standard_types/money.py`,
  `lambdas/CLAUDE.md` / `infra/CLAUDE.md`.
- **`sona-sso-backend`**: `backend/sona_sso/` (all products), `commons/domain/
  value_objects.py` (`PosixTime`), `commons/adapters/orm_base.py` (`TimestampsMixin`),
  `commons/logs.py`, `entrypoints/web/organizations.py` (import style),
  `entrypoints/cron/check_cert_expiry.py` (the negative example for reaching into a value
  object's internals), `CLAUDE.md`, `docs/ARCHITECTURE.md`.
- **`sona` (serverless v1)**: `modules/*_v2/`, `common/`, `common/infrastructure/events/
  base_event_handler.py` (`BaseSQSEventHandler.process_sqs_event` — the starting point for
  the event-consumer pattern, superseded by a design closer to `bold`'s own event-handling
  code once the two dictionaries it requires were identified as the source of `sona`'s own
  documented "unmapped event names" incidents), `ARCHITECTURE_EVENTS.md`, `template*.yaml`.
- **Book**: [_Architecture Patterns with Python_](https://www.cosmicpython.com/) (Cosmic
  Python), source at `github.com/cosmicpython/book`, chapters 1, 2, 4, 6, 7, 8, and
  `appendix_project_structure` — vocabulary and reasoning for Repository, Unit of Work,
  Aggregate, consistency boundaries, ports and adapters, dependency inversion. Where this
  standard deliberately diverges (Order + Stock, `entrypoints-and-orchestration.md` §10.4),
  it says so and explains why.
- **[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)**,
  especially the Imports section — see `enforcement-and-style.md` §17.1.
- **This standard's own author's OOP/design-patterns course material** — see
  `anti-patterns-and-design-principles.md` §22 for which notebook backs which smell/principle.

None of the three real codebases implements this whole stack correctly end-to-end — this
standard is the corrected, unified version, and every correction is explained in terms of
what was wrong with the alternative, not asserted.
