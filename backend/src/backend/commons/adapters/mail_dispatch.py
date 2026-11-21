"""Handler del outbox para `EmailRequested`: entrega con un `Mailer` y, tras enviar, deja
sólo metadatos en el payload guardado (sin cuerpo ni enlaces con token)."""

from typing import Any

from backend.commons.adapters import outbox_dispatcher
from backend.commons.domain import mail

EVENT_TYPE = mail.EmailRequested.__name__


def handler(mailer: mail.Mailer) -> outbox_dispatcher.EventHandler:
    def _handle(payload: dict[str, Any]) -> None:
        event = mail.EmailRequested.model_validate(payload)
        mailer.send(event.message)

    return outbox_dispatcher.EventHandler(handle=_handle, scrub=_scrub)


def _scrub(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message", {})
    return {
        "event_type": payload.get("event_type"),
        "event_id": payload.get("event_id"),
        "occurred_at": payload.get("occurred_at"),
        "category": payload.get("category"),
        "message": {"to": message.get("to"), "subject": message.get("subject"), "scrubbed": True},
    }
