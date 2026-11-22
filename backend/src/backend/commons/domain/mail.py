"""Correo saliente — vocabulario compartido.

Un servicio que quiere enviar un correo NO llama SMTP: registra un `EmailRequested` en el
outbox dentro de su transacción (§11.2). El worker lo entrega con un `Mailer` (puerto) y,
tras enviarlo, borra el cuerpo del payload guardado (los enlaces llevan tokens de un solo
uso; no deben quedarse en la BD en claro)."""

import abc

from backend.commons.domain import events, value_objects


class EmailMessage(value_objects.ValueObject):
    to: str
    subject: str
    text: str
    html: str


class EmailRequested(events.IntegrationEvent):
    """`category` (p. ej. `verify_email`, `password_reset`) sólo sirve para trazas."""

    category: str
    message: EmailMessage


class Mailer(abc.ABC):
    @abc.abstractmethod
    def send(self, message: EmailMessage) -> None:
        """Envía o lanza excepción (el worker reintenta)."""
