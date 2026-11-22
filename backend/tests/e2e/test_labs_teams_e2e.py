"""LD-5: labs (validación, publicación) y equipos (tamaño, uno por lab, bloqueo)."""

import datetime

import pytest

from tests.e2e import conftest as e2e
from tests.e2e import teaching_helpers as h

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF


def test_lab_validation_and_shape(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com")
    course = h.create_course(teacher)
    url = f"{API}/courses/{course['id']}/labs"

    bad_scale = h.error(
        teacher.post(
            url,
            json=h.lab_body(grade_scale={"type": "numeric", "min": 5, "max": 5, "decimals": 3}),
            headers=CSRF,
        ),
        422,
        "validation_error",
    )
    assert set(bad_scale["details"]["fields"]) == {"grade_scale.max", "grade_scale.decimals"}
    out_of_range = h.error(
        teacher.post(
            url,
            json=h.lab_body(grade_scale={"type": "numeric", "min": 0, "max": 5, "pass_mark": 7}),
            headers=CSRF,
        ),
        422,
        "validation_error",
    )
    assert "grade_scale.pass_mark" in out_of_range["details"]["fields"]
    pf_extra = h.error(
        teacher.post(
            url, json=h.lab_body(grade_scale={"type": "pass_fail", "max": 5}), headers=CSRF
        ),
        422,
        "validation_error",
    )
    assert "grade_scale.max" in pf_extra["details"]["fields"]
    no_due = h.error(
        teacher.post(url, json=h.lab_body(deadline_policy="strict"), headers=CSRF),
        422,
        "validation_error",
    )
    assert "due_at" in no_due["details"]["fields"]
    no_size = h.error(
        teacher.post(url, json=h.lab_body(team_mode="team"), headers=CSRF), 422, "validation_error"
    )
    assert "max_team_size" in no_size["details"]["fields"]
    reversed_dates = h.error(
        teacher.post(
            url,
            json=h.lab_body(
                deadline_policy="late_marked",
                opens_at=h.iso(datetime.timedelta(days=3)),
                due_at=h.iso(datetime.timedelta(days=1)),
            ),
            headers=CSRF,
        ),
        422,
        "validation_error",
    )
    assert "opens_at" in reversed_dates["details"]["fields"]

    lab = h.create_lab(
        teacher,
        course["id"],
        publish=False,
        deadline_policy="late_marked",
        due_at=h.iso(datetime.timedelta(days=7)),
        team_mode="team",
        max_team_size=3,
    )
    assert lab["statement_md"] == h.lab_body()["statement_md"]  # tal cual, sin sanear
    assert lab["published_at"] is None and lab["my_submission"] is None
    assert lab["grade_scale"] == {
        "type": "numeric", "min": 0.0, "max": 5.0, "decimals": 1, "pass_mark": 3.0,
    }  # fmt: skip
    patched = h.ok(
        teacher.patch(
            f"{API}/labs/{lab['id']}",
            json={"title": "Lab 1 (v2)", "max_team_size": 2},
            headers=CSRF,
        )
    )
    assert (patched["title"], patched["max_team_size"], patched["team_mode"]) == (
        "Lab 1 (v2)",
        2,
        "team",
    )
    published = h.ok(teacher.post(f"{API}/labs/{lab['id']}/publish", headers=CSRF))
    assert published["published_at"] is not None
    h.error(
        teacher.patch(
            f"{API}/labs/{lab['id']}",
            json={"grade_scale": {"type": "pass_fail"}},
            headers=CSRF,
        ),
        409,
        "lab_published",
    )


def test_unpublished_lab_is_invisible_to_students(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com")
    student = env.signup("s@example.com")
    course = h.create_course(teacher)
    h.enroll(teacher, student, course)
    hidden = h.create_lab(teacher, course["id"], publish=False, title="Borrador")
    visible = h.create_lab(teacher, course["id"], title="Publicado")
    assert [lab["title"] for lab in h.ok(student.get(f"{API}/courses/{course['id']}/labs"))] == [
        "Publicado"
    ]
    assert len(h.ok(teacher.get(f"{API}/courses/{course['id']}/labs"))) == 2
    h.error(student.get(f"{API}/labs/{hidden['id']}"), 404, "not_found")
    h.error(student.get(f"{API}/labs/{hidden['id']}/teams"), 404, "not_found")
    project = h.create_project(student)
    h.error(h.submit(student, hidden["id"], project["id"]), 404, "not_found")
    assert h.ok(student.get(f"{API}/labs/{visible['id']}"))["my_submission"] is None
    h.error(
        student.patch(f"{API}/labs/{visible['id']}", json={"title": "x"}, headers=CSRF),
        403,
        "forbidden",
    )
    h.error(student.post(f"{API}/labs/{visible['id']}/publish", headers=CSRF), 403, "forbidden")
    # Estudiante de OTRO curso: 404.
    other = env.signup("other@example.com")
    h.error(other.get(f"{API}/labs/{visible['id']}"), 404, "not_found")
    assert h.ok(teacher.get(f"{API}/courses/{course['id']}"))["counts"]["labs"] == 2
    assert h.ok(student.get(f"{API}/courses/{course['id']}"))["counts"]["labs"] == 1


def test_teams_size_one_per_lab_lock_and_teacher_reassignment(env: e2e.Env) -> None:
    teacher = env.signup("t@example.com")
    a = env.signup("a@example.com", full_name="Ana")
    b = env.signup("b@example.com", full_name="Beto")
    c = env.signup("c@example.com", full_name="Carla")
    course = h.create_course(teacher)
    ids = {
        name: h.enroll(teacher, client, course) for name, client in (("a", a), ("b", b), ("c", c))
    }
    lab = h.create_lab(teacher, course["id"], team_mode="team", max_team_size=2)
    individual = h.create_lab(teacher, course["id"], title="Individual")
    teams_url = f"{API}/labs/{lab['id']}/teams"

    h.error(
        a.post(f"{API}/labs/{individual['id']}/teams", json={"name": "x"}, headers=CSRF),
        409,
        "not_team_lab",
    )
    h.error(teacher.post(teams_url, json={"name": "Profe"}, headers=CSRF), 403, "forbidden")
    team = h.ok(a.post(teams_url, json={"name": "Los LED"}, headers=CSRF), 201)
    assert set(team) == {
        "id", "lab_id", "name", "locked", "members", "join_code", "created_at", "updated_at",
    }  # fmt: skip
    assert team["members"] == [{"id": ids["a"], "full_name": "Ana"}] and team["join_code"]
    h.error(a.post(teams_url, json={"name": "Otro"}, headers=CSRF), 409, "already_in_team")
    h.error(b.post(f"{teams_url}/join", json={"code": "ZZZZZZ"}, headers=CSRF), 404, "invalid_code")
    joined = h.ok(
        b.post(f"{teams_url}/join", json={"code": team["join_code"].lower()}, headers=CSRF)
    )
    assert [m["full_name"] for m in joined["members"]] == ["Ana", "Beto"]
    h.error(
        c.post(f"{teams_url}/join", json={"code": team["join_code"]}, headers=CSRF),
        409,
        "team_full",
    )
    # Carla no ve el código del equipo ajeno; el docente sí.
    seen_by_c = h.ok(c.get(teams_url))
    assert seen_by_c[0]["join_code"] is None and len(seen_by_c[0]["members"]) == 2
    assert h.ok(teacher.get(teams_url))[0]["join_code"] == team["join_code"]

    other = h.ok(c.post(teams_url, json={"name": "Solo"}, headers=CSRF), 201)
    h.error(
        c.post(f"{teams_url}/join", json={"code": team["join_code"]}, headers=CSRF),
        409,
        "already_in_team",
    )

    locked = h.ok(teacher.post(f"{API}/teams/{team['id']}/lock", headers=CSRF))
    assert locked["locked"] is True
    h.error(a.post(f"{API}/teams/{team['id']}/leave", headers=CSRF), 409, "team_locked")
    h.error(a.post(f"{API}/teams/{team['id']}/lock", headers=CSRF), 403, "forbidden")
    h.error(
        a.put(f"{API}/teams/{team['id']}/members", json=[ids["a"]], headers=CSRF), 403, "forbidden"
    )

    # El docente reasigna (aunque esté bloqueado): Beto pasa al equipo de Carla.
    moved = h.ok(
        teacher.put(f"{API}/teams/{other['id']}/members", json=[ids["c"], ids["b"]], headers=CSRF)
    )
    assert [m["id"] for m in moved["members"]] == [ids["c"], ids["b"]]
    assert [m["id"] for m in h.ok(teacher.get(teams_url))[0]["members"]] == [ids["a"]]
    too_many = h.error(
        teacher.put(
            f"{API}/teams/{other['id']}/members",
            json=[ids["a"], ids["b"], ids["c"]],
            headers=CSRF,
        ),
        422,
        "validation_error",
    )
    assert "members" in too_many["details"]["fields"]
    tid = h.ok(teacher.get(f"{API}/me"))["id"]
    h.error(
        teacher.put(f"{API}/teams/{other['id']}/members", json=[tid], headers=CSRF),
        422,
        "validation_error",
    )
    unlocked = h.ok(teacher.post(f"{API}/teams/{team['id']}/unlock", headers=CSRF))
    assert unlocked["locked"] is False
    left = h.ok(a.post(f"{API}/teams/{team['id']}/leave", headers=CSRF))
    assert left["members"] == []
    h.error(a.post(f"{API}/teams/{team['id']}/leave", headers=CSRF), 409, "not_in_team")
