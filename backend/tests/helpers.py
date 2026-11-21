import re

from backend.commons.domain import mail

_TOKEN_RE = re.compile(r"[?&]t=([A-Za-z0-9_\-]+)")


def token_from_message(message: mail.EmailMessage) -> str:
    match = _TOKEN_RE.search(message.text)
    assert match, f"sin token en el correo: {message.text!r}"
    return match.group(1)


def email_events(
    recorded: list[object], *, to: str | None = None, category: str | None = None
) -> list[mail.EmailRequested]:
    found = [e for e in recorded if isinstance(e, mail.EmailRequested)]
    if to is not None:
        found = [e for e in found if e.message.to == to]
    if category is not None:
        found = [e for e in found if e.category == category]
    return found
