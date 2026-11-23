"""LD-17: avisos por correo de solicitudes de inscripción y aprobaciones (piezas puras)."""

import re

import pytest

from backend.commons.domain import mail
from backend.teaching.commons import ports
from backend.teaching.commons import value_objects as tvo
from backend.teaching.courses.domain.model import aggregate, events
from backend.teaching.courses.domain.model import value_objects as courses_vo
from backend.teaching.courses.services import dto as courses_dto
from backend.teaching.services import emails
from backend.teaching.services import notifications_orchestrator as notifications

pytestmark = pytest.mark.unit

_BASE = "https://lab.example/labdigital"
_COURSE_ID = "0190a5c4-0000-7000-8000-0000000000c1"
_STUDENT = "0190a5c4-0000-7000-8000-0000000000a1"
_T1 = "0190a5c4-0000-7000-8000-0000000000d1"
_T2 = "0190a5c4-0000-7000-8000-0000000000d2"
_COURSE_NAME = "Diseño <Digital> & FPGA"
_ESCAPED_COURSE = "Diseño &lt;Digital&gt; &amp; FPGA"
_STUDENT_NAME = 'Ana "<b>" Pérez'
_ESCAPED_STUDENT = "Ana &quot;&lt;b&gt;&quot; Pérez"
_RUIZ = "ruiz@example.com"
_GIL = "gil@example.com"
_LINK = f"{_BASE}/app/cursos/{_COURSE_ID}"


def _people() -> dict[str, ports.Person]:
    return {
        _STUDENT: ports.Person(id=_STUDENT, full_name=_STUDENT_NAME, email="ana@example.com"),
        _T1: ports.Person(id=_T1, full_name="Profe Ruiz", email=_RUIZ),
        _T2: ports.Person(id=_T2, full_name="Profe Gil", email=_GIL),
    }


def _notice(pending: int = 1) -> courses_dto.MembershipNoticeDTO:
    return courses_dto.MembershipNoticeDTO(
        course_id=_COURSE_ID,
        course_name=_COURSE_NAME,
        period="2027-I",
        student_id=_STUDENT,
        teacher_ids=[_T1, _T2],
        pending=pending,
    )


def _emails(recipients: set[str], pending: int = 1) -> list[mail.EmailRequested]:
    return notifications.join_request_emails(
        notice=_notice(pending), people=_people(), recipients=recipients, public_base_url=_BASE
    )


# ---- El servicio registra el evento (va al outbox con la membresía) --------------------


def _course_ref() -> tvo.CourseId:
    return tvo.CourseId.new()


def _student_ref() -> tvo.UserRef:
    ref = tvo.UserRef.parse(_STUDENT)
    assert ref is not None
    return ref


def test_new_request_records_join_requested() -> None:
    membership = aggregate.Membership.request(course_id=_course_ref(), user_id=_student_ref())
    recorded = membership.pull_events()
    assert [type(e) for e in recorded] == [events.JoinRequested]


@pytest.mark.parametrize(
    "status", [courses_vo.MembershipStatus.REJECTED, courses_vo.MembershipStatus.REMOVED]
)
def test_rerequest_after_rejection_records_a_new_join_requested(
    status: courses_vo.MembershipStatus,
) -> None:
    membership = aggregate.Membership.request(course_id=_course_ref(), user_id=_student_ref())
    membership.status = status
    membership.pull_events()
    assert membership.rerequest()
    assert events.JoinRequested in [type(e) for e in membership.pull_events()]


@pytest.mark.parametrize(
    "status", [courses_vo.MembershipStatus.PENDING, courses_vo.MembershipStatus.ACTIVE]
)
def test_rerequest_when_pending_or_active_records_nothing(
    status: courses_vo.MembershipStatus,
) -> None:
    membership = aggregate.Membership.request(course_id=_course_ref(), user_id=_student_ref())
    membership.status = status
    membership.pull_events()
    assert not membership.rerequest()
    assert membership.pull_events() == []


def test_worker_event_names_come_from_the_event_classes() -> None:
    assert notifications.JOIN_REQUESTED_EVENT == "JoinRequested"
    assert notifications.MEMBERSHIP_STATUS_CHANGED_EVENT == "MembershipStatusChanged"


# ---- Correo al docente ----------------------------------------------------------------


def test_one_email_per_claimed_teacher() -> None:
    requested = _emails({_T1, _T2})
    assert [e.message.to for e in requested] == [_RUIZ, _GIL]
    assert {e.category for e in requested} == {notifications.CATEGORY_JOIN_REQUEST}


def test_throttled_teachers_get_no_email() -> None:
    requested = _emails({_T2})
    assert [e.message.to for e in requested] == [_GIL]
    assert _emails(set()) == []


def test_unknown_student_or_teacher_sends_nothing_for_them() -> None:
    people = _people()
    del people[_T1]
    only_t2 = notifications.join_request_emails(
        notice=_notice(), people=people, recipients={_T1, _T2}, public_base_url=_BASE
    )
    assert [e.message.to for e in only_t2] == [_GIL]
    del people[_STUDENT]
    none = notifications.join_request_emails(
        notice=_notice(), people=people, recipients={_T1, _T2}, public_base_url=_BASE
    )
    assert none == []


def test_join_request_subject_body_and_count() -> None:
    message = _emails({_T1}, pending=3)[0].message
    assert message.subject == f"Nueva solicitud en {_COURSE_NAME} — LabDigital GIDEAM"
    assert "Hola, Profe Ruiz:" in message.text
    assert (
        f"{_STUDENT_NAME} (ana@example.com) pidió unirse a {_COURSE_NAME} (2027-I)." in message.text
    )
    assert "Tienes 3 solicitudes pendientes en este curso." in message.text
    assert "Revisar solicitudes:" in message.text
    assert _LINK in message.text


def test_pending_count_singular() -> None:
    message = _emails({_T1}, pending=1)[0].message
    assert "Tienes 1 solicitud pendiente en este curso." in message.text


def test_join_request_html_escapes_values() -> None:
    body = _emails({_T1})[0].message.html
    assert _COURSE_NAME not in body
    assert _STUDENT_NAME not in body
    assert _ESCAPED_COURSE in body
    assert f"{_ESCAPED_STUDENT} (ana@example.com) pidió unirse" in body
    assert "<title>Nueva solicitud en Diseño &lt;Digital&gt;" in body


def test_join_request_cta_links_to_course() -> None:
    body = _emails({_T1})[0].message.html
    cta = re.search(r'<a href="([^"]+)"[^>]*>Revisar solicitudes</a>', body)
    assert cta is not None
    assert cta.group(1) == _LINK


def test_course_link_ignores_trailing_slash() -> None:
    assert emails.course_link(_BASE + "/", _COURSE_ID) == _LINK


# ---- Correo al estudiante aprobado ----------------------------------------------------


def test_join_approved_email() -> None:
    message = emails.join_approved(
        to="ana@example.com",
        student_name=_STUDENT_NAME,
        course_name=_COURSE_NAME,
        period="2027-I",
        link=_LINK,
    )
    assert message.subject == f"Ya estás en {_COURSE_NAME} — LabDigital GIDEAM"
    assert _ESCAPED_COURSE in message.html
    assert _STUDENT_NAME not in message.html
    cta = re.search(r'<a href="([^"]+)"[^>]*>Ir al curso</a>', message.html)
    assert cta is not None
    assert cta.group(1) == _LINK
