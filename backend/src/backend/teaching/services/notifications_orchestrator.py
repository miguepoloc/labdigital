"""Avisos por correo de inscripciones (LD-17), ejecutados por el worker del outbox.

`courses` ya registra `JoinRequested` (solicitud nueva, o de nuevo tras rechazo/retiro) y
`MembershipStatusChanged` en el outbox, en la misma transacción que la membresía. El worker
los entrega aquí y cada aviso se traduce en `EmailRequested` (uno por destinatario) que
vuelven al outbox: los entrega el handler de correo de siempre, con sus reintentos y el
borrado del cuerpo tras enviar.

- Solicitud ⇒ correo a cada docente activo del curso. Anti-spam: como mucho un correo por
  docente y curso cada `JOIN_NOTICE_THROTTLE`; las solicitudes que llegan dentro de la
  ventana no generan correo propio y cuentan en el «tienes N pendientes» del siguiente.
- Aprobación ⇒ correo «Ya estás en <curso>» al estudiante.

Todo se lee en el momento de avisar: si la solicitud ya se aprobó/rechazó o el curso se
archivó, no se envía nada. Nombres y correos llegan por el puerto `UserDirectory`."""

import datetime
from typing import Any

from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import mail
from backend.teaching.commons import ports
from backend.teaching.courses.services import courses
from backend.teaching.courses.services import dto as courses_dto
from backend.teaching.services import emails

_LOGGER = logs.get_logger()

JOIN_NOTICE_THROTTLE = datetime.timedelta(minutes=10)
CATEGORY_JOIN_REQUEST = "course_join_request"
CATEGORY_JOIN_APPROVED = "course_join_approved"

JOIN_REQUESTED_EVENT = courses.JOIN_REQUESTED_EVENT
MEMBERSHIP_STATUS_CHANGED_EVENT = courses.MEMBERSHIP_STATUS_CHANGED_EVENT


def join_request_emails(
    *,
    notice: courses_dto.MembershipNoticeDTO,
    people: dict[str, ports.Person],
    recipients: set[str],
    public_base_url: str,
) -> list[mail.EmailRequested]:
    """Pura: los correos para los docentes de `recipients` que tengan correo conocido."""
    student = people.get(notice.student_id)
    if student is None:
        return []
    link = emails.course_link(public_base_url, notice.course_id)
    requested = []
    for teacher_id in notice.teacher_ids:
        teacher = people.get(teacher_id)
        if teacher_id not in recipients or teacher is None:
            continue
        message = emails.join_request(
            to=teacher.email,
            teacher_name=teacher.full_name,
            student_name=student.full_name,
            student_email=student.email,
            course_name=notice.course_name,
            period=notice.period,
            pending=notice.pending,
            link=link,
            throttle=JOIN_NOTICE_THROTTLE,
        )
        requested.append(mail.EmailRequested(category=CATEGORY_JOIN_REQUEST, message=message))
    return requested


def notify_join_request(
    *,
    uow: unit_of_work.UnitOfWork,
    directory: ports.UserDirectory,
    public_base_url: str,
    payload: dict[str, Any],
) -> int:
    """Handler de `JoinRequested`. Devuelve cuántos correos dejó en el outbox."""
    notice = courses.join_request_notice(uow=uow, payload=payload)
    if notice is None or not notice.teacher_ids:
        return 0
    people = directory.people([notice.student_id, *notice.teacher_ids])
    with uow.transaction():
        recipients = courses.claim_join_notices(
            uow=uow,
            course_id=notice.course_id,
            teacher_ids=[t for t in notice.teacher_ids if t in people],
            window=JOIN_NOTICE_THROTTLE,
        )
        requested = join_request_emails(
            notice=notice, people=people, recipients=recipients, public_base_url=public_base_url
        )
        for event in requested:
            uow.outbox.record(event)
    skipped = len(notice.teacher_ids) - len(requested)
    if skipped:
        _LOGGER.info("Aviso de solicitud: %s docente(s) sin correo (anti-spam)", skipped)
    return len(requested)


def notify_approval(
    *,
    uow: unit_of_work.UnitOfWork,
    directory: ports.UserDirectory,
    public_base_url: str,
    payload: dict[str, Any],
) -> int:
    """Handler de `MembershipStatusChanged`: sólo actúa en el paso a `active`."""
    notice = courses.approval_notice(uow=uow, payload=payload)
    if notice is None:
        return 0
    student = directory.people([notice.student_id]).get(notice.student_id)
    if student is None:
        return 0
    message = emails.join_approved(
        to=student.email,
        student_name=student.full_name,
        course_name=notice.course_name,
        period=notice.period,
        link=emails.course_link(public_base_url, notice.course_id),
    )
    with uow.transaction():
        uow.outbox.record(mail.EmailRequested(category=CATEGORY_JOIN_APPROVED, message=message))
    return 1
