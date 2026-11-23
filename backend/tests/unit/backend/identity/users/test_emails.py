import re

import pytest

from backend.commons.domain import mail
from backend.identity.users.services import emails
from tests import helpers

pytestmark = pytest.mark.unit

_LINK = "https://lab.example/verificar?t=abc_DEF-123&x=<y>"
_ESCAPED_LINK = "https://lab.example/verificar?t=abc_DEF-123&amp;x=&lt;y&gt;"


def _all() -> list[tuple[str, mail.EmailMessage]]:
    return [
        ("verification", emails.verification(to="a@x.co", full_name="Ada", link=_LINK)),
        ("reset", emails.password_reset(to="a@x.co", full_name="Ada", link=_LINK)),
        (
            "already",
            emails.already_registered(
                to="a@x.co", full_name="Ada", login_link=_LINK, reset_link=_LINK + "r"
            ),
        ),
    ]


@pytest.mark.parametrize(("name", "message"), _all())
def test_html_is_email_safe_shell(name: str, message: mail.EmailMessage) -> None:
    body = message.html
    assert '<html lang="es"' in body
    assert '<meta name="color-scheme" content="light dark">' in body
    assert 'class="ld-preheader"' in body and "display:none" in body
    assert "max-width:600px" in body
    assert "LabDigital" in body and "GIDEAM · Universidad del Magdalena" in body
    assert "https://www.unimagdalena.edu.co/Content/Public/Docs/ManualProteccionDeDatos.pdf" in body
    assert 'href="https://gideam.unimagdalena.edu.co/labdigital/"' in body
    assert "Correo automático, no respondas a este mensaje." in body
    assert "¿El botón no funciona? Copia este enlace:" in body


@pytest.mark.parametrize(("name", "message"), _all())
def test_link_is_escaped_in_html_and_raw_in_text(name: str, message: mail.EmailMessage) -> None:
    assert _LINK not in message.html
    assert f'href="{_ESCAPED_LINK}"' in message.html
    assert _LINK in message.text
    assert "Correo automático, no respondas a este mensaje." in message.text
    assert "https://gideam.unimagdalena.edu.co/labdigital/" in message.text


def test_cta_button_points_to_link() -> None:
    message = emails.verification(to="a@x.co", full_name="Ada", link=_LINK)
    cta = re.search(r'<a href="([^"]+)"[^>]*>Confirmar mi correo</a>', message.html)
    assert cta and cta.group(1) == _ESCAPED_LINK


def test_name_is_escaped() -> None:
    message = emails.verification(to="a@x.co", full_name="<script>x</script>", link=_LINK)
    assert "<script>" not in message.html
    assert "&lt;script&gt;x&lt;/script&gt;" in message.html
    assert "<script>x</script>" in message.text


def test_expiry_comes_from_domain_ttl() -> None:
    assert "vence en 24 horas" in emails.verification(to="a@x.co", full_name="A", link=_LINK).text
    reset = emails.password_reset(to="a@x.co", full_name="A", link=_LINK)
    assert "vence en 30 minutos" in reset.text
    assert "vence en 30 minutos" in reset.html


def test_already_registered_has_both_actions() -> None:
    message = emails.already_registered(
        to="a@x.co",
        full_name="Ada",
        login_link="https://l/entrar",
        reset_link="https://l/recuperar",
    )
    assert re.search(r'<a href="https://l/entrar"[^>]*>Entrar</a>', message.html)
    assert re.search(r'<a href="https://l/recuperar"[^>]*>Recuperar contraseña</a>', message.html)
    assert "https://l/entrar" in message.text and "https://l/recuperar" in message.text


def test_token_still_extractable_from_text() -> None:
    message = emails.password_reset(
        to="a@x.co", full_name="Ada", link="https://l/restablecer?t=tok_1"
    )
    assert helpers.token_from_message(message) == "tok_1"
