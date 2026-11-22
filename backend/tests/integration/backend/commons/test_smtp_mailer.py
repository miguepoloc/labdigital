"""`SmtpMailer` real contra un servidor SMTP local en memoria (aiosmtpd, puerto efímero)."""

import email
from email import policy
import socket

from aiosmtpd import controller as smtpd_controller
import pytest

from backend.commons.adapters import mailer, settings
from backend.commons.domain import mail

pytestmark = pytest.mark.integration


class _Sink:
    def __init__(self) -> None:
        self.messages: list[email.message.EmailMessage] = []

    async def handle_DATA(self, server: object, session: object, envelope: object) -> str:  # noqa: N802
        content = envelope.content  # type: ignore[attr-defined]
        self.messages.append(email.message_from_bytes(content, policy=policy.default))  # type: ignore[arg-type]
        return "250 OK"


def test_smtp_mailer_sends_multipart_spanish_mail() -> None:
    sink = _Sink()
    with socket.socket() as probe:  # puerto libre efímero (> 18000, fuera de 8000-8099)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = smtpd_controller.Controller(sink, hostname="127.0.0.1", port=port)
    server.start()
    try:
        cfg = settings.get_settings().model_copy(
            update={"smtp_host": "127.0.0.1", "smtp_port": port, "smtp_starttls": False}
        )
        mailer.SmtpMailer(cfg).send(
            mail.EmailMessage(
                to="ana@example.com",
                subject="Confirma tu correo",
                text="Hola, Ána",
                html="<p>Hola, Ána</p>",
            )
        )
    finally:
        server.stop()
    (received,) = sink.messages
    assert received["To"] == "ana@example.com" and received["Subject"] == "Confirma tu correo"
    assert received.get_body(("plain",)).get_content().strip() == "Hola, Ána"  # type: ignore[union-attr]
    assert "<p>Hola, Ána</p>" in received.get_body(("html",)).get_content()  # type: ignore[union-attr]
