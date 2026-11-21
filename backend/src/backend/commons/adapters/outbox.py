"""Transactional Outbox — ARCHITECTURE.md §11.2. `OutboxRepository.record` is called
inside the same `with uow.transaction():` as the aggregate write (see commons.domain
.aggregates.AggregateRoot.pull_events + every subcontext's services/<name>.py). A separate
relay (an EventBridge-scheduled cron entrypoint) reads unpublished rows and publishes
IntegrationEvent rows to SNS."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.commons.adapters import orm_base
from backend.commons.domain import events, value_objects


class OutboxRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, event: events.DomainEvent) -> None:
        """Records every DomainEvent for audit/replay, but only IntegrationEvent rows are
        ever relayed out (§11.1/§11.2) — the relay filters by event_type at publish time."""
        self._session.add(
            orm_base.OutboxEventOrm(
                event_type=event.event_type,
                payload=event.model_dump(mode="json"),
                idempotence_key=event.idempotence_key(),
                created_at=value_objects.PosixTime.now().microseconds,
                published_at=None,
            )
        )

    def unpublished(self, *, limit: int = 100) -> list[orm_base.OutboxEventOrm]:
        """Used by the relay cron entrypoint — see identity/entrypoints/cron and
        commerce/entrypoints/cron for the per-product relay."""
        stmt = (
            select(orm_base.OutboxEventOrm)
            .where(orm_base.OutboxEventOrm.published_at.is_(None))
            .order_by(orm_base.OutboxEventOrm.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self._session.scalars(stmt))

    def mark_published(self, row: orm_base.OutboxEventOrm) -> None:
        """For use on a row already loaded in this session (e.g. a non-IntegrationEvent row
        skipped in the same read as `unpublished()`, ARCHITECTURE.md §11.1) — a plain
        attribute write, no query."""
        row.published_at = value_objects.PosixTime.now().microseconds

    def mark_many_published(self, row_ids: list[uuid.UUID]) -> None:
        """For use in a *separate* transaction from the one that read the rows (the outbox
        relay's second, post-publish transaction — see outbox_relay.py) — the ORM instances
        from that first transaction's session are gone, so this updates by id instead of
        requiring a loaded row."""
        if not row_ids:
            return
        self._session.execute(
            update(orm_base.OutboxEventOrm)
            .where(orm_base.OutboxEventOrm.id.in_(row_ids))
            .values(published_at=value_objects.PosixTime.now().microseconds)
        )
