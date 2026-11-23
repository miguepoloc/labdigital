#!/usr/bin/env python3
"""Renderiza los correos transaccionales a ficheros HTML/TXT para revisarlos a ojo.

Uso (desde backend/):  uv run python scripts/preview_emails.py [DIRECTORIO]
Por defecto escribe en `./email-previews/`. Datos ficticios; no envía nada."""

import pathlib
import sys

from backend.identity.users.services import emails

_BASE = "https://gideam.unimagdalena.edu.co/labdigital"
_TOKEN = "Zx8Q-ejemplo_token_de_un_solo_uso_3f9a1c7b2d4e6f8091a2b3c4d5e6f7a8"


def main() -> None:
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "email-previews")
    out.mkdir(parents=True, exist_ok=True)
    messages = {
        "verification": emails.verification(
            to="ada@example.com", full_name="Ada Lovelace", link=f"{_BASE}/verificar?t={_TOKEN}"
        ),
        "reset": emails.password_reset(
            to="ada@example.com", full_name="Ada Lovelace", link=f"{_BASE}/restablecer?t={_TOKEN}"
        ),
        "already": emails.already_registered(
            to="ada@example.com",
            full_name="Ada Lovelace",
            login_link=f"{_BASE}/entrar",
            reset_link=f"{_BASE}/recuperar",
        ),
    }
    for name, message in messages.items():
        (out / f"{name}.html").write_text(message.html, encoding="utf-8")
        (out / f"{name}.txt").write_text(f"Asunto: {message.subject}\n\n{message.text}", "utf-8")
        print(out / f"{name}.html")


if __name__ == "__main__":
    main()
