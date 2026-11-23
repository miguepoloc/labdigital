"""Plantillas de correo de `teaching` (LD-17): aviso al docente de una solicitud de
inscripción y aviso al estudiante cuando lo aprueban. Funciones puras sobre la maquetación
compartida (`commons.application.email_layout`, la misma de los correos de `identity`)."""

import datetime

from backend.commons.application import email_layout
from backend.commons.domain import mail

_SUFFIX = " — LabDigital GIDEAM"


def course_link(public_base_url: str, course_id: str) -> str:
    """Página del curso en el frontend (`/app/cursos/:id`, pestaña «Solicitudes» incluida)."""
    return f"{public_base_url.rstrip('/')}/app/cursos/{course_id}"


def _pending_text(pending: int) -> str:
    if pending == 1:
        return "Tienes 1 solicitud pendiente en este curso."
    return f"Tienes {pending} solicitudes pendientes en este curso."


def _minutes(window: datetime.timedelta) -> int:
    return int(window.total_seconds() // 60)


def join_request(
    *,
    to: str,
    teacher_name: str,
    student_name: str,
    student_email: str,
    course_name: str,
    period: str,
    pending: int,
    link: str,
    throttle: datetime.timedelta,
) -> mail.EmailMessage:
    return email_layout.message(
        to=to,
        subject=f"Nueva solicitud en {course_name}{_SUFFIX}",
        preheader=f"{student_name} quiere unirse a {course_name}. {_pending_text(pending)}",
        title="Nueva solicitud de inscripción",
        greeting=f"Hola, {teacher_name}:",
        paragraphs=[
            f"{student_name} ({student_email}) pidió unirse a {course_name} ({period}).",
            "Revisa la pestaña «Solicitudes» del curso para aprobarla o rechazarla.",
        ],
        primary=email_layout.Action("Revisar solicitudes", link),
        notice=_pending_text(pending),
        security=f"Recibes este correo porque eres docente de {course_name}. Para no llenar "
        f"tu bandeja te avisamos como máximo una vez cada {_minutes(throttle)} minutos por "
        "curso; el número de pendientes siempre está al día en LabDigital.",
    )


def join_approved(
    *, to: str, student_name: str, course_name: str, period: str, link: str
) -> mail.EmailMessage:
    return email_layout.message(
        to=to,
        subject=f"Ya estás en {course_name}{_SUFFIX}",
        preheader=f"Tu docente aprobó tu solicitud para {course_name}.",
        title=f"Ya estás en {course_name}",
        greeting=f"¡Hola, {student_name}!",
        paragraphs=[
            f"Tu docente aprobó tu solicitud para unirte a {course_name} ({period}).",
            "Ya puedes ver los laboratorios publicados y hacer tus entregas.",
        ],
        primary=email_layout.Action("Ir al curso", link),
        notice="Entra con tu cuenta de LabDigital para ver el curso.",
        security="Recibes este correo porque pediste unirte a este curso en LabDigital GIDEAM.",
    )
