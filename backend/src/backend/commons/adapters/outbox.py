"""Transactional Outbox — ARCHITECTURE.md §11.2. `OutboxRepository.record` se llama dentro
del mismo `with uow.transaction():` que la escritura del agregado. El worker
(`backend.entrypoints.worker`) usa `claim_batch`/`mark_delivered`/`mark_retry` vía
`outbox_dispatcher.dispatch_pending`."""

from typing import Any
import uuid

import sqlalchemy as sa
from sqlalchemy import orm

from backend.commons.adapters import orm_base
from backend.commons.domain import events, value_objects


class ClaimedEvent:
    """Copia desacoplada de la sesión de una fila reclamada (la sesión se cierra antes de
    hacer I/O externa)."""

    def __init__(
        self, *, row_id: uuid.UUID, event_type: str, payload: dict[str, Any], attempts: int
    ) -> None:
        self.row_id = row_id
        self.event_type = event_type
        self.payload = payload
        self.attempts = attempts


class OutboxRepository:
    def __init__(self, session: orm.Session) -> None:
        self._session = session

    def record(self, event: events.DomainEvent) -> None:
        """Registra todo DomainEvent (auditoría/reproceso); el worker sólo hace algo con los
        tipos que tiene registrados y marca el resto como publicados sin más."""
        now = value_objects.PosixTime.now().microseconds
        self._session.add(
            orm_base.OutboxEventOrm(
                event_type=event.event_type,
                payload=event.model_dump(mode="json"),
                idempotence_key=event.idempotence_key(),
                created_at=now,
                published_at=None,
                attempts=0,
                next_attempt_at=0,
            )
        )

    def claim_batch(self, *, limit: int, lease_microseconds: int) -> list[ClaimedEvent]:
        """Reclama hasta `limit` filas pendientes (`FOR UPDATE SKIP LOCKED`) y empuja su
        `next_attempt_at` `lease_microseconds` al futuro. Debe confirmarse la transacción
        antes de hacer I/O con lo reclamado."""
        now = value_objects.PosixTime.now().microseconds
        stmt = (
            sa.select(orm_base.OutboxEventOrm)
            .where(
                orm_base.OutboxEventOrm.published_at.is_(None),
                orm_base.OutboxEventOrm.failed_at.is_(None),
                orm_base.OutboxEventOrm.next_attempt_at <= now,
            )
            .order_by(orm_base.OutboxEventOrm.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        claimed: list[ClaimedEvent] = []
        for row in self._session.scalars(stmt):
            row.attempts += 1
            row.next_attempt_at = now + lease_microseconds
            claimed.append(
                ClaimedEvent(
                    row_id=row.id,
                    event_type=row.event_type,
                    payload=dict(row.payload),
                    attempts=row.attempts,
                )
            )
        return claimed

    def mark_delivered(
        self, row_id: uuid.UUID, *, scrubbed_payload: dict[str, Any] | None = None
    ) -> None:
        values: dict[str, Any] = {
            "published_at": value_objects.PosixTime.now().microseconds,
            "last_error": None,
        }
        if scrubbed_payload is not None:
            values["payload"] = scrubbed_payload
        self._session.execute(
            sa.update(orm_base.OutboxEventOrm)
            .where(orm_base.OutboxEventOrm.id == row_id)
            .values(**values)
        )

    def mark_retry(self, row_id: uuid.UUID, *, error: str, retry_at: int | None) -> None:
        """`retry_at=None` ⇒ fallo definitivo (`failed_at`)."""
        values: dict[str, Any] = {"last_error": error[:2000]}
        if retry_at is None:
            values["failed_at"] = value_objects.PosixTime.now().microseconds
        else:
            values["next_attempt_at"] = retry_at
        self._session.execute(
            sa.update(orm_base.OutboxEventOrm)
            .where(orm_base.OutboxEventOrm.id == row_id)
            .values(**values)
        )
