"""SMTP falso para tests: un `Mailer` que captura en memoria."""

from backend.commons.domain import mail


class CapturingMailer(mail.Mailer):
    def __init__(self) -> None:
        self.sent: list[mail.EmailMessage] = []
        self.fail_next = 0

    def send(self, message: mail.EmailMessage) -> None:
        if self.fail_next:
            self.fail_next -= 1
            raise ConnectionError("SMTP caído (simulado)")
        self.sent.append(message)

    def to(self, address: str) -> list[mail.EmailMessage]:
        return [m for m in self.sent if m.to == address]
