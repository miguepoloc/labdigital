"""Audit log adapter — ARCHITECTURE.md §14.2. `AuditRepository.add` is called inside the
same `with uow.transaction():` as the aggregate write it's recording, same pattern as
`OutboxRepository.record` (commons/adapters/outbox.py). No abstract port in `commons/domain`:
this mirrors `OutboxRepository` itself, which also has none — neither is something a
domain/services unit test fakes, both are generic infra invoked by the same boilerplate
every service already goes through."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.commons.adapters import orm_base
from backend.commons.domain import audit, value_objects


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: audit.AuditEntry) -> None:
        self._session.add(
            orm_base.AuditLogOrm(
                actor_id=entry.actor.id,
                actor_label=entry.actor.label,
                action=entry.action,
                aggregate_type=entry.aggregate_type,
                aggregate_id=entry.aggregate_id,
                changes=entry.changes,
                created_at=value_objects.PosixTime.now().microseconds,
            )
        )

    def list_for_aggregate(
        self, aggregate_type: str, aggregate_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[audit.AuditEntry]:
        """Descending by `created_at` — answers "what happened to this order/user/sku",
        the query `sona-sso-backend`'s real `list_for_org`-only API can't answer for its own
        `console_auth` login/logout rows (written with `org_id=None`, permanently
        unreachable through that API)."""
        stmt = (
            select(orm_base.AuditLogOrm)
            .where(
                orm_base.AuditLogOrm.aggregate_type == aggregate_type,
                orm_base.AuditLogOrm.aggregate_id == aggregate_id,
            )
            .order_by(orm_base.AuditLogOrm.created_at.desc(), orm_base.AuditLogOrm.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_to_entry(row) for row in self._session.scalars(stmt)]


def _to_entry(row: orm_base.AuditLogOrm) -> audit.AuditEntry:
    return audit.AuditEntry(
        id=row.id,
        actor=audit.Actor(id=row.actor_id, label=row.actor_label),
        action=row.action,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        changes=dict(row.changes),
        created_at=value_objects.PosixTime(microseconds=row.created_at),
    )
