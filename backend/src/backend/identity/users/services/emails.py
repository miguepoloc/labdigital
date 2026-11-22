"""Plantillas de correo (español, texto + HTML sencillo). Funciones puras: devuelven un
`EmailMessage` que el servicio registra en el outbox."""

import html

from backend.commons.domain import mail

_FOOTER_TEXT = (
    "\n\n—\nLabDigital GIDEAM · Universidad del Magdalena\n"
    "Si no solicitaste este correo, puedes ignorarlo."
)


def _html(
    title: str, greeting: str, body: str, action_label: str | None, action_url: str | None
) -> str:
    button = ""
    if action_label and action_url:
        url = html.escape(action_url, quote=True)
        button = (
            f'<p style="margin:24px 0"><a href="{url}" style="background:#004B87;color:#ffffff;'
            f'padding:12px 20px;border-radius:6px;text-decoration:none;font-weight:600">'
            f"{html.escape(action_label)}</a></p>"
            f'<p style="font-size:13px;color:#555">Si el botón no funciona, copia este enlace en '
            f'tu navegador:<br><a href="{url}">{url}</a></p>'
        )
    return (
        '<!doctype html><html lang="es"><body style="font-family:Roboto,Arial,sans-serif;'
        'color:#1a1a1a;max-width:560px;margin:0 auto;padding:24px">'
        f'<h1 style="font-size:20px;color:#004B87">{html.escape(title)}</h1>'
        f"<p>{html.escape(greeting)}</p><p>{html.escape(body)}</p>{button}"
        '<hr style="border:none;border-top:1px solid #ddd;margin:24px 0">'
        '<p style="font-size:12px;color:#777">LabDigital GIDEAM · Universidad del Magdalena.<br>'
        "Si no solicitaste este correo, puedes ignorarlo.</p></body></html>"
    )


def verification(*, to: str, full_name: str, link: str) -> mail.EmailMessage:
    greeting = f"Hola, {full_name}:"
    body = (
        "Gracias por registrarte en LabDigital GIDEAM. Para activar tu cuenta confirma tu "
        "correo con el siguiente enlace. El enlace vence en 24 horas."
    )
    return mail.EmailMessage(
        to=to,
        subject="Confirma tu correo — LabDigital GIDEAM",
        text=f"{greeting}\n\n{body}\n\n{link}{_FOOTER_TEXT}",
        html=_html("Confirma tu correo", greeting, body, "Confirmar correo", link),
    )


def password_reset(*, to: str, full_name: str, link: str) -> mail.EmailMessage:
    greeting = f"Hola, {full_name}:"
    body = (
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta de LabDigital "
        "GIDEAM. Usa el siguiente enlace para elegir una nueva; vence en 30 minutos y sólo "
        "puede usarse una vez. Al cambiarla se cerrarán todas tus sesiones abiertas."
    )
    return mail.EmailMessage(
        to=to,
        subject="Restablece tu contraseña — LabDigital GIDEAM",
        text=f"{greeting}\n\n{body}\n\n{link}{_FOOTER_TEXT}",
        html=_html("Restablece tu contraseña", greeting, body, "Elegir nueva contraseña", link),
    )


def already_registered(
    *, to: str, full_name: str, login_link: str, reset_link: str
) -> mail.EmailMessage:
    greeting = f"Hola, {full_name}:"
    body = (
        "Alguien intentó crear una cuenta de LabDigital GIDEAM con este correo, pero ya "
        "tienes una. Puedes entrar normalmente o, si olvidaste la contraseña, pedir una nueva."
    )
    return mail.EmailMessage(
        to=to,
        subject="Ya tienes una cuenta — LabDigital GIDEAM",
        text=(
            f"{greeting}\n\n{body}\n\nEntrar: {login_link}\nRecuperar contraseña: {reset_link}"
            f"{_FOOTER_TEXT}"
        ),
        html=_html("Ya tienes una cuenta", greeting, body, "Entrar", login_link),
    )
