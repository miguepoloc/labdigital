"""Despachador del outbox — ARCHITECTURE.md §11.2, adaptado a un worker de proceso
siempre encendido (sin SNS/SQS).

Tres pasos, nunca I/O externa con una transacción abierta (persistence-and-concurrency §8):
1. transacción corta: reclamar un lote (lease de `_LEASE`);
2. sin transacción: ejecutar el handler de cada evento (p. ej. enviar el correo);
3. transacción corta por evento: marcar entregado o programar reintento.

Entrega *al menos una vez*: si el worker muere entre 2 y 3 el evento se reintenta al
vencer el lease. Los handlers deben tolerarlo (un correo duplicado es aceptable).
"""

from collections.abc import Callable, Mapping
import dataclasses
import datetime
from typing import Any

from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import value_objects

_LOGGER = logs.get_logger()
_LEASE = datetime.timedelta(minutes=5)
_MAX_ATTEMPTS = 8
_MICROS = 1_000_000


@dataclasses.dataclass(frozen=True)
class EventHandler:
    """`handle` recibe el payload JSON del evento. `scrub` (opcional) devuelve el payload a
    conservar tras entregar — p. ej. sin el enlace con token del correo."""

    handle: Callable[[dict[str, Any]], None]
    scrub: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def dispatch_pending(
    uow: unit_of_work.UnitOfWork,
    *,
    handlers: Mapping[str, EventHandler],
    batch_size: int = 20,
) -> int:
    """Procesa un lote. Devuelve cuántas filas se reclamaron (0 ⇒ no queda nada listo). Los
    tipos sin handler se marcan entregados sin hacer nada (eventos internos, §11.1)."""
    with uow.transaction():
        claimed = uow.outbox.claim_batch(
            limit=batch_size, lease_microseconds=int(_LEASE.total_seconds() * _MICROS)
        )

    delivered = 0
    for event in claimed:
        handler = handlers.get(event.event_type)
        if handler is None:
            with uow.transaction():
                uow.outbox.mark_delivered(event.row_id)
            continue
        try:
            handler.handle(event.payload)
        except Exception as exc:  # noqa: BLE001 — cualquier fallo del handler se reintenta
            retry_at = _retry_at(event.attempts)
            _LOGGER.warning(
                "Outbox: fallo en %s (intento %s): %s", event.event_type, event.attempts, exc
            )
            with uow.transaction():
                uow.outbox.mark_retry(event.row_id, error=repr(exc), retry_at=retry_at)
            continue
        scrubbed = handler.scrub(event.payload) if handler.scrub else None
        with uow.transaction():
            uow.outbox.mark_delivered(event.row_id, scrubbed_payload=scrubbed)
        delivered += 1

    if delivered:
        _LOGGER.info("Outbox: %s evento(s) entregado(s)", delivered)
    return len(claimed)


def _retry_at(attempts: int) -> int | None:
    if attempts >= _MAX_ATTEMPTS:
        return None
    delay_seconds: int = min(30 * 2 ** (attempts - 1), 3600)
    return value_objects.PosixTime.now().microseconds + delay_seconds * _MICROS
