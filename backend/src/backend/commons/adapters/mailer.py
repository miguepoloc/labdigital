"""Adaptador SMTP del puerto `commons.domain.mail.Mailer` (Brevo en producción)."""

from email import message as email_message
from email import utils as email_utils
import smtplib
import ssl

from backend.commons.adapters import settings
from backend.commons.domain import mail


class SmtpMailer(mail.Mailer):
    def __init__(self, app_settings: settings.Settings | None = None) -> None:
        self._settings = app_settings or settings.get_settings()

    def send(self, message: mail.EmailMessage) -> None:
        cfg = self._settings
        msg = email_message.EmailMessage()
        msg["From"] = cfg.mail_from
        msg["To"] = message.to
        msg["Subject"] = message.subject
        msg["Date"] = email_utils.formatdate(localtime=False)
        msg["Message-ID"] = email_utils.make_msgid(domain=_domain_of(cfg.mail_from))
        msg.set_content(message.text)
        msg.add_alternative(message.html, subtype="html")

        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds) as smtp:
            if cfg.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if cfg.smtp_user:
                smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)


def _domain_of(address: str) -> str:
    _, addr = email_utils.parseaddr(address)
    return addr.rsplit("@", 1)[-1] if "@" in addr else "localhost"
