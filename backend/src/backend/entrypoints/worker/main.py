"""Worker de proceso: consume el outbox (correos por SMTP, avisos de inscripción de
`teaching`) y hace housekeeping periódico.

    python -m backend.entrypoints.worker.main

Un bucle simple (sin cola externa): cada `WORKER_POLL_SECONDS` despacha un lote; cada hora
limpia sesiones/tokens/contadores caducados. SIGTERM/SIGINT terminan tras el lote en curso.
"""

import signal
import threading
import time
from types import FrameType
from typing import Any

from backend.commons.adapters import (
    logs,
    mail_dispatch,
    mailer,
    outbox_dispatcher,
    settings,
    unit_of_work,
)
from backend.commons.domain import mail
from backend.identity.entrypoints.cron import housekeeping
from backend.orchestrators import ports
from backend.teaching.commons import ports as teaching_ports
from backend.teaching.services import notifications_orchestrator as notifications

_LOGGER = logs.get_logger()
_HOUSEKEEPING_EVERY_SECONDS = 3600


def build_handlers(
    mail_port: mail.Mailer,
    *,
    directory: teaching_ports.UserDirectory | None = None,
    public_base_url: str | None = None,
) -> dict[str, outbox_dispatcher.EventHandler]:
    """Correo saliente + avisos de inscripción (LD-17), que dejan sus correos en el outbox
    para el handler de correo (cada uno con su propia unidad de trabajo)."""
    users = directory or ports.IdentityUserDirectory()
    base_url = (public_base_url or settings.get_settings().public_base_url).rstrip("/")

    def _join_requested(payload: dict[str, Any]) -> None:
        notifications.notify_join_request(
            uow=unit_of_work.build(), directory=users, public_base_url=base_url, payload=payload
        )

    def _status_changed(payload: dict[str, Any]) -> None:
        notifications.notify_approval(
            uow=unit_of_work.build(), directory=users, public_base_url=base_url, payload=payload
        )

    return {
        mail_dispatch.EVENT_TYPE: mail_dispatch.handler(mail_port),
        notifications.JOIN_REQUESTED_EVENT: outbox_dispatcher.EventHandler(handle=_join_requested),
        notifications.MEMBERSHIP_STATUS_CHANGED_EVENT: outbox_dispatcher.EventHandler(
            handle=_status_changed
        ),
    }


def run_once(
    uow: unit_of_work.UnitOfWork, handlers: dict[str, outbox_dispatcher.EventHandler]
) -> int:
    """Despacha lotes hasta vaciar lo pendiente. Lo usan el bucle y los tests."""
    total = 0
    while True:
        processed = outbox_dispatcher.dispatch_pending(uow, handlers=handlers)
        total += processed
        if processed == 0:
            return total


def prune_rate_limits(uow: unit_of_work.UnitOfWork) -> int:
    with uow.transaction():
        return uow.rate_limits.prune() + uow.backoff.prune()


def main() -> None:
    app_settings = settings.get_settings()
    stop = threading.Event()

    def _stop(signum: int, _frame: FrameType | None) -> None:
        _LOGGER.info("Worker: señal %s recibida, terminando", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    handlers = build_handlers(mailer.SmtpMailer(app_settings))
    uow = unit_of_work.build()
    next_housekeeping = 0.0
    _LOGGER.info("Worker iniciado (cada %ss)", app_settings.worker_poll_seconds)
    while not stop.is_set():
        try:
            run_once(uow, handlers)
            if time.monotonic() >= next_housekeeping:
                housekeeping.run(uow)
                prune_rate_limits(uow)
                next_housekeeping = time.monotonic() + _HOUSEKEEPING_EVERY_SECONDS
        except Exception:  # noqa: BLE001 — el worker no muere por un fallo transitorio
            _LOGGER.exception("Worker: error en la iteración")
        stop.wait(app_settings.worker_poll_seconds)
    _LOGGER.info("Worker detenido")


if __name__ == "__main__":
    main()
