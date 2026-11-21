"""LD-4: cursos, código de unión, aprobación y permisos cruzados."""

import pytest

from tests.e2e import conftest as e2e
from tests.e2e import teaching_helpers as h

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF


def test_join_pending_then_approve_and_course_shapes(env: e2e.Env) -> None:
    teacher = env.signup("docente@example.com", full_name="Profe Ruiz")
    student = env.signup("ana@example.com", full_name="Ana Pérez")
    course = h.create_course(teacher)
    assert set(course) >= {
        "id", "name", "period", "description", "archived_at", "owner_id", "owner_name",
        "my_role", "my_status", "join_code", "counts",
    }  # fmt: skip
    assert (course["my_role"], course["my_status"], course["owner_name"]) == (
        "docente",
        "active",
        "Profe Ruiz",
    )
    code = course["join_code"]
    assert len(code) == 9 and code[4] == "-"
    assert not set(code.replace("-", "")) & set("01OIL")

    # El código se acepta en minúsculas y sin guion.
    joined = h.ok(
        student.post(
            f"{API}/courses/join", json={"code": code.replace("-", "").lower()}, headers=CSRF
        )
    )
    assert (joined["my_role"], joined["my_status"], joined["join_code"]) == (
        "estudiante",
        "pending",
        None,
    )
    # Pendiente: repetir es idempotente.
    assert (
        h.ok(student.post(f"{API}/courses/join", json={"code": code}, headers=CSRF))["my_status"]
        == "pending"
    )

    listed = h.ok(teacher.get(f"{API}/courses"))
    assert listed[0]["counts"] == {"students": 0, "pending": 1, "labs": 0}
    pending = h.ok(
        teacher.get(f"{API}/courses/{course['id']}/members", params={"status": "pending"})
    )
    assert [(m["full_name"], m["email"]) for m in pending] == [("Ana Pérez", "ana@example.com")]

    # Pendiente no ve labs ni gestiona nada.
    h.error(student.get(f"{API}/courses/{course['id']}/labs"), 403, "forbidden")
    h.ok(
        teacher.post(
            f"{API}/courses/{course['id']}/members/{pending[0]['user_id']}/approve", headers=CSRF
        )
    )
    mine = h.ok(student.get(f"{API}/courses"))
    assert [(c["id"], c["my_role"], c["my_status"], c["join_code"]) for c in mine] == [
        (course["id"], "estudiante", "active", None)
    ]
    assert h.ok(teacher.get(f"{API}/courses/{course['id']}"))["counts"]["students"] == 1
    h.error(
        student.post(f"{API}/courses/join", json={"code": code}, headers=CSRF),
        409,
        "already_member",
    )
    h.error(
        teacher.post(f"{API}/courses/join", json={"code": code}, headers=CSRF),
        409,
        "already_member",
    )


def test_invalid_code_rotation_reject_remove_and_archive(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com")
    student = env.signup("s@example.com")
    course = h.create_course(teacher)
    h.error(
        student.post(f"{API}/courses/join", json={"code": "ZZZZ-ZZZZ"}, headers=CSRF),
        404,
        "invalid_code",
    )
    h.error(
        student.post(f"{API}/courses/join", json={"code": "0000"}, headers=CSRF),
        404,
        "invalid_code",
    )
    rotated = h.ok(teacher.post(f"{API}/courses/{course['id']}/join-code/rotate", headers=CSRF))
    assert rotated["join_code"] != course["join_code"]
    h.error(
        student.post(f"{API}/courses/join", json={"code": course["join_code"]}, headers=CSRF),
        404,
        "invalid_code",
    )
    h.ok(student.post(f"{API}/courses/join", json={"code": rotated["join_code"]}, headers=CSRF))
    sid = h.ok(student.get(f"{API}/me"))["id"]
    rejected = h.ok(
        teacher.post(f"{API}/courses/{course['id']}/members/{sid}/reject", headers=CSRF)
    )
    assert rejected["status"] == "rejected"
    # Rechazado: el curso sigue en su lista (con estado) pero no puede verlo.
    assert h.ok(student.get(f"{API}/courses"))[0]["my_status"] == "rejected"
    h.error(student.get(f"{API}/courses/{course['id']}"), 404, "not_found")
    # Vuelve a pedirlo ⇒ pendiente otra vez; aprobar; retirar.
    h.ok(student.post(f"{API}/courses/join", json={"code": rotated["join_code"]}, headers=CSRF))
    h.ok(teacher.post(f"{API}/courses/{course['id']}/members/{sid}/approve", headers=CSRF))
    removed = h.ok(teacher.post(f"{API}/courses/{course['id']}/members/{sid}/remove", headers=CSRF))
    assert removed["status"] == "removed"
    h.error(
        teacher.post(f"{API}/courses/{course['id']}/members/{sid}/reject", headers=CSRF),
        409,
        "invalid_transition",
    )
    tid = h.ok(teacher.get(f"{API}/me"))["id"]
    h.error(
        teacher.post(f"{API}/courses/{course['id']}/members/{tid}/remove", headers=CSRF),
        409,
        "invalid_transition",
    )
    archived = h.ok(
        teacher.patch(f"{API}/courses/{course['id']}", json={"archived": True}, headers=CSRF)
    )
    assert archived["archived_at"] is not None
    h.error(
        student.post(f"{API}/courses/join", json={"code": rotated["join_code"]}, headers=CSRF),
        404,
        "invalid_code",
    )
    h.error(
        teacher.patch(f"{API}/courses/{course['id']}", json={"name": "Otro"}, headers=CSRF),
        409,
        "course_archived",
    )
    h.error(
        teacher.post(f"{API}/courses/{course['id']}/labs", json=h.lab_body(), headers=CSRF),
        409,
        "course_archived",
    )
    assert (
        h.ok(
            teacher.patch(f"{API}/courses/{course['id']}", json={"archived": False}, headers=CSRF)
        )["archived_at"]
        is None
    )


def test_cross_course_permissions(env: e2e.Env) -> None:
    teacher_a = env.signup("ta@example.com")
    teacher_b = env.signup("tb@example.com")
    student_a = env.signup("sa@example.com")
    outsider = env.signup("out@example.com")
    course = h.create_course(teacher_a)
    sid = h.enroll(teacher_a, student_a, course)
    cid = course["id"]
    for client in (teacher_b, outsider):
        h.error(client.get(f"{API}/courses/{cid}"), 404, "not_found")
        h.error(client.get(f"{API}/courses/{cid}/members"), 404, "not_found")
        h.error(client.get(f"{API}/courses/{cid}/labs"), 404, "not_found")
        h.error(client.get(f"{API}/courses/{cid}/grades.csv"), 404, "not_found")
        h.error(
            client.post(f"{API}/courses/{cid}/members/{sid}/remove", headers=CSRF), 404, "not_found"
        )
    # Estudiante del curso: lo ve, pero no gestiona (403).
    h.ok(student_a.get(f"{API}/courses/{cid}"))
    h.error(student_a.get(f"{API}/courses/{cid}/members"), 403, "forbidden")
    h.error(
        student_a.patch(f"{API}/courses/{cid}", json={"name": "x"}, headers=CSRF), 403, "forbidden"
    )
    h.error(student_a.post(f"{API}/courses/{cid}/join-code/rotate", headers=CSRF), 403, "forbidden")
    h.error(
        student_a.post(f"{API}/courses/{cid}/labs", json=h.lab_body(), headers=CSRF),
        403,
        "forbidden",
    )
    # Admin lo ve todo (sin rol en el curso; no ve el código).
    admin = env.signup(e2e_admin_email())
    seen = h.ok(admin.get(f"{API}/courses/{cid}"))
    assert (seen["my_role"], seen["join_code"]) == (None, None)
    assert len(h.ok(admin.get(f"{API}/courses/{cid}/members"))) == 2
    assert env.make_client().get(f"{API}/courses").status_code == 401


def e2e_admin_email() -> str:
    from tests import conftest  # noqa: PLC0415

    return conftest.ADMIN_EMAIL
