"""Plantillas de correo de `identity` (verificación, restablecer contraseña, ya registrado).

Funciones puras sobre la maquetación compartida (`commons.application.email_layout`):
devuelven un `EmailMessage` que el servicio registra en el outbox."""

import datetime

from backend.commons.application import email_layout
from backend.commons.domain import mail
from backend.identity.users.domain.model import aggregate


def _ttl_text(ttl: datetime.timedelta) -> str:
    minutes = int(ttl.total_seconds() // 60)
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hora" if hours == 1 else f"{hours} horas"
    return f"{minutes} minuto" if minutes == 1 else f"{minutes} minutos"


# ---------------------------------------------------------------------------------------
# Correos
# ---------------------------------------------------------------------------------------


def verification(*, to: str, full_name: str, link: str) -> mail.EmailMessage:
    ttl = _ttl_text(aggregate.VERIFY_EMAIL_TTL)
    return email_layout.message(
        to=to,
        subject="Confirma tu correo — LabDigital GIDEAM",
        preheader=f"Un clic y tu cuenta de LabDigital queda activa. El enlace vence en {ttl}.",
        title="Confirma tu correo",
        greeting=f"¡Hola, {full_name}!",
        paragraphs=[
            "Gracias por registrarte en LabDigital GIDEAM, el laboratorio digital de "
            "Ingeniería Electrónica de la Universidad del Magdalena.",
            "Para activar tu cuenta solo falta confirmar que este correo es tuyo:",
        ],
        primary=email_layout.Action("Confirmar mi correo", link),
        notice=f"El enlace vence en {ttl}. Si caduca, puedes pedir uno nuevo desde la "
        "página de inicio de sesión.",
    )


def password_reset(*, to: str, full_name: str, link: str) -> mail.EmailMessage:
    ttl = _ttl_text(aggregate.PASSWORD_RESET_TTL)
    return email_layout.message(
        to=to,
        subject="Restablece tu contraseña — LabDigital GIDEAM",
        preheader=f"Elige una nueva contraseña para LabDigital. El enlace vence en {ttl}.",
        title="Restablece tu contraseña",
        greeting=f"Hola, {full_name}:",
        paragraphs=[
            "Recibimos una solicitud para restablecer la contraseña de tu cuenta de "
            "LabDigital GIDEAM. Usa el botón para elegir una nueva.",
            "Al cambiarla se cerrarán todas tus sesiones abiertas.",
        ],
        primary=email_layout.Action("Elegir nueva contraseña", link),
        notice=f"El enlace vence en {ttl} y solo puede usarse una vez.",
        security="Si no solicitaste este correo, puedes ignorarlo: tu contraseña actual "
        "sigue funcionando.",
    )


def already_registered(
    *, to: str, full_name: str, login_link: str, reset_link: str
) -> mail.EmailMessage:
    return email_layout.message(
        to=to,
        subject="Ya tienes una cuenta — LabDigital GIDEAM",
        preheader="Alguien intentó registrarse con tu correo, pero ya tienes una cuenta.",
        title="Ya tienes una cuenta",
        greeting=f"Hola, {full_name}:",
        paragraphs=[
            "Alguien intentó crear una cuenta de LabDigital GIDEAM con este correo, pero "
            "ya tienes una.",
            "Puedes entrar normalmente o, si olvidaste la contraseña, pedir una nueva.",
        ],
        primary=email_layout.Action("Entrar", login_link),
        secondary=email_layout.Action("Recuperar contraseña", reset_link),
        notice="No se creó ninguna cuenta nueva ni se cambió nada en la tuya.",
        security="Si no fuiste tú, puedes ignorar este correo: nadie puede entrar sin tu "
        "contraseña.",
    )
