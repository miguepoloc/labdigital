"""LD-17 con Postgres real: outbox → aviso al docente (anti-spam) → correo; aprobación →
correo al estudiante."""

import datetime
import uuid

import pytest
import sqlalchemy as sa
import time_machine

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.entrypoints.worker import main as worker
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users
from backend.teaching.commons import value_objects as tvo
from backend.teaching.courses.domain.model import aggregate as courses_aggregate
from backend.teaching.courses.domain.model import value_objects as courses_vo
from backend.teaching.courses.services import courses
from backend.teaching.courses.services import dto as courses_dto
from tests import capturing
from tests.unit.backend.identity import builders

pytestmark = pytest.mark.integration

_ACTOR = audit.Actor(id=None, label="test")
_BASE = "https://lab.example/labdigital"
_T = "t@example.com"
_S = "s@example.com"
_APPROVED_SUBJECT = "Ya estás en Curso — LabDigital GIDEAM"
_LD17 = ("Nueva solicitud en ", "Ya estás en ")


class _World:
    def __init__(self) -> None:
        self.uow = unit_of_work.build()
        self.mailer = capturing.CapturingMailer()
        self.handlers = worker.build_handlers(self.mailer, public_base_url=_BASE)

    def deliver(self) -> None:
        worker.run_once(self.uow, self.handlers)

    def user(self, email: str) -> tvo.Viewer:
        users.register(
            uow=self.uow,
            input_dto=users_dto.RegisterInputDTO(
                email=email,
                full_name=f"Nombre {email.split('@')[0]}",
                password="caballo-bateria-grapa",
                accept_data_policy=True,
            ),
            config=builders.CONFIG,
            context=users_dto.RequestContext(ip=f"10.1.{uuid.uuid4().int % 250}.1"),
        )
        with self.uow.transaction():
            uid = self.uow.session.execute(
                sa.text("SELECT id FROM users WHERE email = :e"), {"e": email}
            ).scalar_one()
        return tvo.Viewer(user_id=tvo.UserRef(value=uid))

    def course(self, teacher: tvo.Viewer) -> courses_dto.CourseOutputDTO:
        created = courses.create_course(
            uow=self.uow,
            viewer=teacher,
            actor=_ACTOR,
            input_dto=courses_dto.CreateCourseInputDTO(name="Curso", period="2027-I"),
        )
        self.deliver()  # correos de registro fuera
        self.mailer.sent.clear()
        return created

    def join(self, student: tvo.Viewer, course: courses_dto.CourseOutputDTO) -> None:
        assert course.join_code is not None
        courses.join(uow=self.uow, viewer=student, actor=_ACTOR, code=course.join_code)

    def decide(
        self,
        teacher: tvo.Viewer,
        course: courses_dto.CourseOutputDTO,
        student: tvo.Viewer,
        decision: courses_vo.MembershipDecision,
    ) -> None:
        courses.decide_membership(
            uow=self.uow,
            viewer=teacher,
            actor=_ACTOR,
            course_id=course.id,
            user_id=str(student.user_id),
            decision=decision,
        )

    def subjects(self, address: str) -> list[str]:
        """Sólo los avisos de LD-17 (fuera los correos de verificación del registro)."""
        return [m.subject for m in self.mailer.to(address) if m.subject.startswith(_LD17)]


def _later(minutes: int) -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes)


def test_teacher_is_notified_once_per_window_with_running_count(db: sa.Engine) -> None:
    w = _World()
    teacher = w.user(_T)
    course = w.course(teacher)
    w.join(w.user("s1@example.com"), course)
    w.deliver()
    first = w.mailer.to(_T)
    assert [m.subject for m in first] == ["Nueva solicitud en Curso — LabDigital GIDEAM"]
    assert "Nombre s1 (s1@example.com) pidió unirse a Curso (2027-I)." in first[0].text
    assert "Tienes 1 solicitud pendiente en este curso." in first[0].text
    assert f"{_BASE}/app/cursos/{course.id}" in first[0].text

    # Dentro de la ventana: sin correo nuevo.
    w.join(w.user("s2@example.com"), course)
    w.deliver()
    assert len(w.mailer.to(_T)) == 1

    # Pasada la ventana, el siguiente aviso lleva el total de pendientes.
    with time_machine.travel(_later(11), tick=True):
        w.join(w.user("s3@example.com"), course)
        w.deliver()
    latest = w.mailer.to(_T)
    assert len(latest) == 2
    assert "Tienes 3 solicitudes pendientes en este curso." in latest[-1].text
    assert "Nombre s3 (s3@example.com)" in latest[-1].text


def test_every_active_teacher_of_the_course_is_notified(db: sa.Engine) -> None:
    w = _World()
    owner = w.user("t1@example.com")
    co_teacher = w.user("t2@example.com")
    course = w.course(owner)
    with w.uow.transaction():
        w.uow.repo(courses_aggregate.Membership).add(
            courses_aggregate.Membership.for_teacher(
                course_id=tvo.CourseId(value=uuid.UUID(course.id)), user_id=co_teacher.user_id
            )
        )
    w.join(w.user(_S), course)
    w.deliver()
    assert len(w.subjects("t1@example.com")) == 1
    assert len(w.subjects("t2@example.com")) == 1
    assert w.subjects(_S) == []


def test_request_decided_before_the_worker_runs_is_not_announced(db: sa.Engine) -> None:
    w = _World()
    teacher = w.user(_T)
    student = w.user(_S)
    course = w.course(teacher)
    w.join(student, course)
    w.decide(teacher, course, student, courses_vo.MembershipDecision.APPROVE)
    w.deliver()
    assert w.subjects(_T) == []
    approved = w.mailer.to(_S)
    assert [m.subject for m in approved] == [_APPROVED_SUBJECT]
    assert f"{_BASE}/app/cursos/{course.id}" in approved[0].text


def test_rejected_student_asking_again_notifies_again(db: sa.Engine) -> None:
    w = _World()
    teacher = w.user(_T)
    student = w.user(_S)
    course = w.course(teacher)
    w.join(student, course)
    w.deliver()
    w.decide(teacher, course, student, courses_vo.MembershipDecision.REJECT)
    w.join(student, course)  # dentro de la ventana: anti-spam
    w.deliver()
    assert len(w.subjects(_T)) == 1
    with time_machine.travel(_later(11), tick=True):
        w.decide(teacher, course, student, courses_vo.MembershipDecision.REJECT)
        w.join(student, course)
        w.deliver()
    assert len(w.subjects(_T)) == 2
    # Repetir la solicitud pendiente no genera nada.
    w.join(student, course)
    w.deliver()
    assert len(w.subjects(_T)) == 2
    # Ni rechazar ni volver a pedir avisan al estudiante; aprobar sí.
    assert w.subjects(_S) == []
    w.decide(teacher, course, student, courses_vo.MembershipDecision.APPROVE)
    w.deliver()
    assert w.subjects(_S) == [_APPROVED_SUBJECT]


def test_join_emails_are_scrubbed_after_sending(db: sa.Engine) -> None:
    w = _World()
    teacher = w.user(_T)
    course = w.course(teacher)
    w.join(w.user(_S), course)
    w.deliver()
    with w.uow.transaction():
        rows = w.uow.session.execute(
            sa.text(
                "SELECT payload FROM outbox_events WHERE event_type = 'EmailRequested' "
                "AND payload->>'category' = 'course_join_request'"
            )
        ).scalars()
        payloads = list(rows)
    assert len(payloads) == 1
    assert payloads[0]["message"]["scrubbed"] is True
    assert payloads[0]["message"]["to"] == _T
