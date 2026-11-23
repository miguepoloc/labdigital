"""LD-17 de punta a punta: pedir unirse (HTTP) → worker → correo al docente; aprobar →
correo al estudiante."""

import re

import pytest

from tests import conftest as root_conftest
from tests.e2e import conftest as e2e
from tests.e2e import teaching_helpers as h

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF
_TEACHER = "docente@example.com"
_STUDENT = "ana@example.com"


def test_join_request_emails_teacher_and_approval_emails_student(env: e2e.Env) -> None:
    teacher = env.signup(_TEACHER, full_name="Profe Ruiz")
    student = env.signup(_STUDENT, full_name="Ana <Pérez>")
    course = h.create_course(teacher, name="Diseño Digital")
    env.deliver()
    before = len(env.mailer.to(_TEACHER))

    h.ok(student.post(f"{API}/courses/join", json={"code": course["join_code"]}, headers=CSRF))
    # Repetir la solicitud pendiente es idempotente: ni evento ni correo nuevos.
    h.ok(student.post(f"{API}/courses/join", json={"code": course["join_code"]}, headers=CSRF))
    env.deliver()

    notices = env.mailer.to(_TEACHER)[before:]
    assert [m.subject for m in notices] == ["Nueva solicitud en Diseño Digital — LabDigital GIDEAM"]
    notice = notices[0]
    link = f"{root_conftest.PUBLIC_BASE_URL}/app/cursos/{course['id']}"
    assert "Ana <Pérez> (ana@example.com) pidió unirse a Diseño Digital (2027-I)." in notice.text
    assert "Ana &lt;Pérez&gt; (ana@example.com)" in notice.html
    assert "Tienes 1 solicitud pendiente en este curso." in notice.text
    cta = re.search(r'<a href="([^"]+)"[^>]*>Revisar solicitudes</a>', notice.html)
    assert cta is not None
    assert cta.group(1) == link

    me = h.ok(student.get(f"{API}/me"))
    h.ok(teacher.post(f"{API}/courses/{course['id']}/members/{me['id']}/approve", headers=CSRF))
    env.deliver()
    approved = [m for m in env.mailer.to(_STUDENT) if m.subject.startswith("Ya estás en")]
    assert [m.subject for m in approved] == ["Ya estás en Diseño Digital — LabDigital GIDEAM"]
    assert link in approved[0].text
    assert len(env.mailer.to(_TEACHER)) == before + 1
