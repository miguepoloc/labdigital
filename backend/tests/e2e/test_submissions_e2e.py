"""LD-6: entregas (individual, equipo, tardía, estricta, re-entrega), versión congelada,
revisión con escala, archivos (límite, firma, autorización) y notas CSV."""

import datetime

import pytest

from tests.e2e import conftest as e2e
from tests.e2e import teaching_helpers as h

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF
DAY = datetime.timedelta(days=1)


def test_individual_submission_freezes_version_review_and_resubmission(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com", full_name="Profe")
    student = env.signup("s@example.com", full_name="Sara")
    course = h.create_course(teacher)
    sid = h.enroll(teacher, student, course)
    lab = h.create_lab(teacher, course["id"])
    project = h.create_project(student, "entregado")
    pid = project["id"]
    report = h.ok(h.upload(student, "informe.pdf", h.PDF, "report"), 201)
    bit = h.ok(h.upload(student, "top.bit", h.BIT, "bitstream"), 201)
    assert set(report) >= {"id", "sha256", "size", "mime"} and report["mime"] == "application/pdf"

    # Profe no entrega.
    h.error(h.submit(teacher, lab["id"], pid), 403, "forbidden")
    created = h.ok(h.submit(student, lab["id"], pid, file_ids=[report["id"], bit["id"]]), 201)
    assert (created["attempt"], created["status"], created["is_late"], created["grade"]) == (
        1,
        "submitted",
        False,
        None,
    )
    assert created["version_id"] == project["current_version_id"] and created["version_n"] == 1
    assert created["submitted_by"] == {"id": sid, "full_name": "Sara"} and created["team"] is None
    assert created["content"]["files"][0]["text"] == "entregado"
    assert [(f["kind"], f["name"]) for f in created["files"]] == [
        ("report", "informe.pdf"),
        ("bitstream", "top.bit"),
    ]

    # La versión entregada NO cambia con más autoguardados (dentro de la ventana de 10 min).
    for i in range(3):
        h.autosave(student, pid, f"después {i}")
    detail = h.ok(student.get(f"{API}/submissions/{created['id']}"))
    assert detail["content"]["files"][0]["text"] == "entregado"
    versions = h.ok(student.get(f"{API}/projects/{pid}/versions"))
    assert [(v["n"], v["kind"]) for v in versions] == [(2, "autosave"), (1, "submitted")]
    frozen = h.ok(student.get(f"{API}/projects/{pid}/versions/{versions[1]['id']}"))
    assert frozen["content"]["files"][0]["text"] == "entregado"

    # Lab sin re-entrega: 409.
    h.error(h.submit(student, lab["id"], pid), 409, "resubmission_not_allowed")
    lab_view = h.ok(student.get(f"{API}/labs/{lab['id']}"))
    assert lab_view["my_submission"]["id"] == created["id"]

    # Nota fuera de escala ⇒ 422 con details.fields.grade.
    for bad in (5.5, -1, 4.25, "x"):
        body = h.error(
            h.review(teacher, created["id"], grade=bad, comment=""), 422, "validation_error"
        )
        assert "grade" in body["details"]["fields"]
    h.error(h.review(student, created["id"], grade=4, comment="yo"), 403, "forbidden")
    returned = h.ok(
        h.review(
            teacher, created["id"], comment="Falta el testbench", return_for_resubmission=True
        ),
        201,
    )
    assert returned["status"] == "returned"
    assert returned["reviews"][0]["reviewer_name"] == "Profe"

    # Devuelta ⇒ re-entrega permitida aunque el lab no la admita.
    second = h.ok(h.submit(student, lab["id"], pid), 201)
    assert second["attempt"] == 2 and second["version_n"] == 2
    graded = h.ok(h.review(teacher, second["id"], grade=4.5, comment="Bien"), 201)
    assert (graded["status"], graded["grade"]) == ("graded", 4.5)
    h.error(h.submit(student, lab["id"], pid), 409, "resubmission_not_allowed")
    listed = h.ok(student.get(f"{API}/labs/{lab['id']}/submissions"))
    assert [s["attempt"] for s in listed] == [2, 1] and "content" not in listed[0]


def test_team_submission_any_member_and_visibility(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com")
    other_teacher = env.signup("t2@example.com")
    a = env.signup("a@example.com", full_name="Ana")
    b = env.signup("b@example.com", full_name="Beto")
    c = env.signup("c@example.com", full_name="Carla")
    course = h.create_course(teacher)
    for client in (a, b, c):
        h.enroll(teacher, client, course)
    lab = h.create_lab(
        teacher, course["id"], team_mode="team", max_team_size=3, allow_resubmission=True
    )
    project = h.create_project(b)
    h.error(h.submit(b, lab["id"], project["id"]), 409, "team_required")
    team = h.ok(a.post(f"{API}/labs/{lab['id']}/teams", json={"name": "LED"}, headers=CSRF), 201)
    h.ok(
        b.post(f"{API}/labs/{lab['id']}/teams/join", json={"code": team["join_code"]}, headers=CSRF)
    )

    created = h.ok(h.submit(b, lab["id"], project["id"]), 201)  # Beto entrega por el equipo
    assert created["team"] == {"id": team["id"], "name": "LED"}
    assert [m["full_name"] for m in created["members"]] == ["Ana", "Beto"]
    assert h.ok(a.get(f"{API}/submissions/{created['id']}"))["content"]["format"]
    assert h.ok(a.get(f"{API}/labs/{lab['id']}"))["my_submission"]["id"] == created["id"]
    # Re-entrega (lab la permite) desde Ana con SU proyecto: intento 2 del mismo equipo.
    second = h.ok(h.submit(a, lab["id"], h.create_project(a)["id"]), 201)
    assert second["attempt"] == 2
    # No integrantes, docente de otro curso, anónimo: no la ven.
    h.error(c.get(f"{API}/submissions/{created['id']}"), 404, "not_found")
    assert h.ok(c.get(f"{API}/labs/{lab['id']}/submissions")) == []
    h.error(other_teacher.get(f"{API}/submissions/{created['id']}"), 404, "not_found")
    h.error(other_teacher.get(f"{API}/labs/{lab['id']}/submissions"), 404, "not_found")
    assert env.make_client().get(f"{API}/submissions/{created['id']}").status_code == 401
    assert len(h.ok(teacher.get(f"{API}/labs/{lab['id']}/submissions"))) == 2
    # Proyecto ajeno: 404 (sólo se entregan proyectos propios).
    h.error(h.submit(a, lab["id"], project["id"]), 404, "not_found")


def test_deadlines_late_strict_returned_and_not_open(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com")
    student = env.signup("s@example.com")
    course = h.create_course(teacher)
    h.enroll(teacher, student, course)
    pid = h.create_project(student)["id"]
    late = h.create_lab(
        teacher,
        course["id"],
        title="Tardía",
        deadline_policy="late_marked",
        opens_at=h.iso(-3 * DAY),
        due_at=h.iso(-DAY),
    )
    strict = h.create_lab(
        teacher, course["id"], title="Estricta", deadline_policy="strict", due_at=h.iso(-DAY)
    )
    future = h.create_lab(
        teacher,
        course["id"],
        title="Futura",
        deadline_policy="strict",
        opens_at=h.iso(DAY),
        due_at=h.iso(3 * DAY),
    )
    on_time = h.create_lab(
        teacher, course["id"], title="A tiempo", deadline_policy="strict", due_at=h.iso(DAY)
    )
    assert h.ok(h.submit(student, late["id"], pid), 201)["is_late"] is True
    assert h.ok(h.submit(student, on_time["id"], pid), 201)["is_late"] is False
    h.error(h.submit(student, strict["id"], pid), 409, "deadline_passed")
    h.error(h.submit(student, future["id"], pid), 409, "lab_not_open")

    # Estricta ya cerrada, pero el docente devolvió la entrega: se admite (y queda tardía).
    reopened = h.ok(
        teacher.patch(f"{API}/labs/{strict['id']}", json={"due_at": h.iso(DAY)}, headers=CSRF)
    )
    first = h.ok(h.submit(student, reopened["id"], pid), 201)
    h.ok(teacher.patch(f"{API}/labs/{strict['id']}", json={"due_at": h.iso(-DAY)}, headers=CSRF))
    h.ok(h.review(teacher, first["id"], comment="Corrige", return_for_resubmission=True), 201)
    again = h.ok(h.submit(student, strict["id"], pid), 201)
    assert (again["attempt"], again["is_late"]) == (2, True)


def test_files_limits_fake_type_and_download_authorization(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com")
    other_teacher = env.signup("t2@example.com")
    student = env.signup("s@example.com")
    stranger = env.signup("x@example.com")
    course = h.create_course(teacher)
    h.enroll(teacher, student, course)
    lab = h.create_lab(teacher, course["id"])

    fake = h.error(
        h.upload(student, "informe.pdf", b"MZ\x90\x00 no soy un pdf"), 422, "validation_error"
    )
    assert "file" in fake["details"]["fields"]
    h.error(h.upload(student, "virus.exe", b"MZ\x90"), 422, "validation_error")
    h.error(h.upload(student, "foto.png", h.PNG, "bitstream"), 422, "validation_error")
    h.error(h.upload(student, "vacio.bit", b"", "bitstream"), 422, "validation_error")
    # Justo por encima de 25 MB: pasa el middleware (25 MB + margen) y lo corta el servicio.
    big = h.upload(student, "grande.bit", b"\x00" * (25 * 1024 * 1024 + 1), "bitstream")
    h.error(big, 413, "payload_too_large")
    huge = h.upload(student, "enorme.bit", b"\x00" * (26 * 1024 * 1024), "bitstream")
    h.error(huge, 413, "payload_too_large")
    # El límite de 3 MB sigue para el JSON del resto de rutas.
    assert (
        student.post(
            f"{API}/projects",
            content=b"{" + b" " * (4 * 1024 * 1024) + b"}",
            headers={**CSRF, "Content-Type": "application/json"},
        ).status_code
        == 413
    )

    photo = h.ok(h.upload(student, "foto.png", h.PNG), 201)
    unused = h.ok(h.upload(student, "otra.png", h.PNG), 201)
    assert photo["sha256"] == unused["sha256"] and photo["id"] != unused["id"]  # mismo contenido
    stranger_file = h.ok(h.upload(stranger, "suyo.png", h.PNG), 201)
    project = h.create_project(student)
    h.error(
        h.submit(student, lab["id"], project["id"], file_ids=[stranger_file["id"]]),
        404,
        "not_found",
    )
    created = h.ok(h.submit(student, lab["id"], project["id"], file_ids=[photo["id"]]), 201)
    assert created["files"][0]["mime"] == "image/png"

    url = f"{API}/files/{photo['id']}"
    own = student.get(url)
    assert own.status_code == 200 and own.content == h.PNG
    assert own.headers["content-type"] == "image/png"
    assert own.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in own.headers["content-disposition"]
    assert teacher.get(url).status_code == 200  # docente del curso de la entrega
    h.error(teacher.get(f"{API}/files/{unused['id']}"), 404, "not_found")  # no entregado
    h.error(other_teacher.get(url), 404, "not_found")
    h.error(stranger.get(url), 404, "not_found")
    h.error(stranger.get(f"{API}/files/no-es-un-id"), 404, "not_found")
    assert env.make_client().get(url).status_code == 401


def test_grades_csv_excel_es_co(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com")
    ana = env.signup("ana@example.com", full_name="Ana Pérez")
    beto = env.signup("beto@example.com", full_name="=Beto")
    course = h.create_course(teacher, name="Diseño Digital")
    h.enroll(teacher, ana, course)
    h.enroll(teacher, beto, course)
    numeric = h.create_lab(teacher, course["id"], title="Lab 1", allow_resubmission=True)
    passfail = h.create_lab(
        teacher, course["id"], title="Lab 2; equipo", grade_scale={"type": "pass_fail"}
    )
    pid = h.create_project(ana)["id"]
    first = h.ok(h.submit(ana, numeric["id"], pid), 201)
    h.ok(h.review(teacher, first["id"], grade=3, comment=""), 201)
    second = h.ok(h.submit(ana, numeric["id"], pid), 201)
    h.ok(h.review(teacher, second["id"], grade=4.5, comment=""), 201)
    pf = h.ok(h.submit(ana, passfail["id"], pid), 201)
    graded = h.ok(h.review(teacher, pf["id"], grade=1, comment=""), 201)
    assert graded["grade"] == 1
    h.error(h.review(teacher, pf["id"], grade=0.5, comment=""), 422, "validation_error")

    h.error(ana.get(f"{API}/courses/{course['id']}/grades.csv"), 403, "forbidden")
    response = teacher.get(f"{API}/courses/{course['id']}/grades.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "notas-dise" in response.headers["content-disposition"]
    raw = response.content
    assert raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8-sig").split("\r\n")
    assert lines[0] == 'Nombre;Correo;Lab 1;"Lab 2; equipo"'
    assert lines[1] == "'=Beto;beto@example.com;;"  # sin notas; fórmula neutralizada
    assert lines[2] == "Ana Pérez;ana@example.com;4,5;Aprobado"
