"""Worker de proceso: consume el outbox (correos por SMTP) y hace housekeeping periódico.

    python -m backend.entrypoints.worker.main

Un bucle simple (sin cola externa): cada `WORKER_POLL_SECONDS` despacha un lote; cada hora
limpia sesiones/tokens/contadores caducados. SIGTERM/SIGINT terminan tras el lote en curso.
"""

import signal
import threading
import time
from types import FrameType

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

_LOGGER = logs.get_logger()
_HOUSEKEEPING_EVERY_SECONDS = 3600


def build_handlers(mail_port: mail.Mailer) -> dict[str, outbox_dispatcher.EventHandler]:
    return {mail_dispatch.EVENT_TYPE: mail_dispatch.handler(mail_port)}


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
        return uow.rate_limits.prune()


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
