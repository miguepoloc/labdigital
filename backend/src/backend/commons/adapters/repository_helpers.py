"""Shared repository helpers — ARCHITECTURE.md §5.2/§7/§11.2.

`insert_with_id_retry` is only needed for aggregates keyed by `HumanFriendlyId` (a short
random string, rare PK collision possible); `UuidV7Id`-keyed aggregates never need it.
`publish_events` is called by every concrete repository's `add`/`update` — see
`domain-and-application.md`/ARCHITECTURE.md §7 for why event publishing lives here now
instead of a hand-called `_publish_events()` helper in every services/*.py file."""

from typing import Protocol

import sqlalchemy.exc
from sqlalchemy.orm import Session

from backend.commons.adapters import outbox as outbox_module
from backend.commons.domain import aggregates, exceptions, value_objects

_MAX_ID_COLLISION_RETRIES = 3


class _HumanFriendlyIdRow(Protocol):
    """Minimal shape of an ORM row with a `HumanFriendlyId` primary key: a `str` id
    (`HumanFriendlyId.value: str`, ARCHITECTURE.md §5.2 — every `HumanFriendlyId`-keyed ORM
    row has one) plus `__tablename__`. SQLAlchemy 2.0's `Mapped[str]` satisfies a plain
    `id: str` here structurally, no SQLAlchemy mypy plugin needed."""

    __tablename__: str
    id: str


def insert_with_id_retry[RowT: _HumanFriendlyIdRow](session: Session, row: RowT) -> str:
    """Inserts `row`, regenerating `row.id` on primary key collision.

    Verified against `sona-sso-backend`'s real `insert_with_id_retry`: uses
    `session.begin_nested()` (a SAVEPOINT) so a failed attempt rolls back only that one
    INSERT, not the whole outer transaction — a plain `session.rollback()` on a caught
    `IntegrityError`, as an earlier draft of this helper did, would discard every other
    write already staged in the same `with uow.transaction():` block, not just this one.

    Mutates `row` in place and returns the final id string — the caller must sync it back
    onto the domain entity if it changed (`entity.id = value_objects.OrderId(value=final_id)`).

    Raises:
        ConflictError: if a unique id can't be found within `_MAX_ID_COLLISION_RETRIES`.
    """
    table_name = row.__tablename__
    primary_key_constraint = f"{table_name}_pkey"  # Postgres's own default naming for an
    # inline PRIMARY KEY column constraint — this codebase sets no custom naming_convention
    # on Base.metadata (commons/adapters/orm_base.py), so this is what Postgres actually names it.
    for attempt in range(_MAX_ID_COLLISION_RETRIES):
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            return row.id
        except sqlalchemy.exc.IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
            if constraint != primary_key_constraint:
                raise
            if attempt == _MAX_ID_COLLISION_RETRIES - 1:
                raise exceptions.ConflictError(
                    f"Could not generate a unique id for [{table_name}] after "
                    f"{_MAX_ID_COLLISION_RETRIES} attempts.",
                    code="ID_COLLISION",
                    retriable=True,
                ) from exc
            row.id = value_objects.HumanFriendlyId.new().value
    raise AssertionError("unreachable")  # noqa: EM101


def publish_events(session: Session, entity: aggregates.AggregateRoot) -> None:
    """The shared tail of every concrete `Repository[T].add`/`.update`: drain the entity's
    recorded events and record them to the outbox, in the same transaction as the write
    that just happened. Centralizing this here (rather than a `_publish_events()` helper
    hand-called in every services/*.py function) means a service can no longer forget to
    call it — `add`/`update` do it unconditionally, matching bold's own documented
    lifecycle: 'Repository persists atomically: save(aggregate) calls uow.publish(event)
    inside a transaction' (`lambdas/CLAUDE.md`)."""
    outbox_repo = outbox_module.OutboxRepository(session)
    for event in entity.pull_events():
        outbox_repo.record(event)
