"""Shared SQLAlchemy declarative base + the tables commons/ itself owns — ARCHITECTURE.md
§7/§11.2/§12. One shared metadata object; Alembic's target_metadata points at Base.metadata."""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampsMixin:
    """created_at/updated_at in POSIX microseconds (BigInteger) — never `datetime`
    (ARCHITECTURE.md §1.8)."""

    created_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)


class IdempotencyKeyOrm(Base):
    """ARCHITECTURE.md §12.1/§12.2 — one shared table for `UnitOfWork.transaction
    (idempotency_key=...)`'s single mechanism (claim a key inside the same transaction as
    the effect, let a unique constraint deduplicate), used identically by both call sites:
    a client's HTTP `Idempotency-Key` header (§12.1) and an event's
    `event.idempotence_key()` (§12.2). Two use cases, one table, one code path — see
    `unit_of_work.py::UnitOfWork._claim_idempotency_key`."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    created_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)


class AuditLogOrm(Base):
    """ARCHITECTURE.md §14.2 — the shared audit log. `id` uses `sa.Identity()` (a real
    Postgres sequence), not the `HumanFriendlyId` every aggregate uses elsewhere: an
    append-only log with no growth ceiling is exactly the case a random-10-character scheme
    isn't sized for. No FK on `aggregate_id`/`actor_id` — this row must outlive whatever it
    references. `aggregate_type`/`aggregate_id`, not `entity_type`/`entity_id`: every write
    site sits where `uow.repo(...).add`/`.update` does — the aggregate root being persisted,
    matching this codebase's own `Entity`/`AggregateRoot` distinction (commons/domain/
    entities.py vs aggregates.py)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        sa.Index("ix_audit_log_aggregate", "aggregate_type", "aggregate_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(nullable=True, index=True)
    actor_label: Mapped[str] = mapped_column(sa.Text, nullable=False)
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)


class OutboxEventOrm(Base):
    """ARCHITECTURE.md §11.2 — the Transactional Outbox. Written in the same transaction
    as the aggregate mutation; a separate relay reads unpublished rows and publishes."""

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    idempotence_key: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    created_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    published_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
