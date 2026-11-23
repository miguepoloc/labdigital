"""LD-18: el docente crea, renombra, borra y organiza los equipos de un lab en equipo.

Caso real: «Digitales 2», lab «Proyecto final» en parejas (`max_team_size=2`)."""

from typing import Any

from fastapi import testclient
import pytest
import sqlalchemy as sa

from backend.commons.adapters import engine, orm_base
from tests.e2e import conftest as e2e
from tests.e2e import teaching_helpers as h

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF
FORBIDDEN = "forbidden"
CONFLICT = 409
VALIDATION = "validation_error"
NOT_FOUND = "not_found"
PAIR_1 = "Pareja 1"
PAIR_2 = "Pareja 2"


def _setup(
    env: e2e.Env, names: tuple[str, ...]
) -> tuple[testclient.TestClient, dict[str, Any], dict[str, str], dict[str, testclient.TestClient]]:
    teacher = env.signup("docente@example.com", full_name="Profe")
    course = h.create_course(teacher, name="Digitales 2")
    clients = {n: env.signup(f"{n.lower()}@example.com", full_name=n) for n in names}
    ids = {n: h.enroll(teacher, c, course) for n, c in clients.items()}
    lab = h.create_lab(
        teacher, course["id"], title="Proyecto final", team_mode="team", max_team_size=2
    )
    return teacher, lab, ids, clients


def _member_ids(team: dict[str, Any]) -> list[str]:
    return [m["id"] for m in team["members"]]


def _teams_by_name(teacher: testclient.TestClient, lab_id: str) -> dict[str, dict[str, Any]]:
    return {t["name"]: t for t in h.ok(teacher.get(f"{API}/labs/{lab_id}/teams"))}


def test_teacher_bulk_creates_pairs_and_organizes_students(env: e2e.Env) -> None:
    teacher, lab, ids, _ = _setup(env, ("Ana", "Beto", "Carla", "Dani", "Eva"))
    teams_url = f"{API}/labs/{lab['id']}/teams"

    # Todos sin equipo, por nombre.
    unassigned = h.ok(teacher.get(f"{teams_url}/unassigned"))
    assert [p["full_name"] for p in unassigned] == ["Ana", "Beto", "Carla", "Dani", "Eva"]

    created = h.ok(teacher.post(f"{teams_url}/bulk", json={"count": 12}, headers=CSRF), 201)
    assert [t["name"] for t in created] == [f"Pareja {i}" for i in range(1, 13)]
    assert all(t["members"] == [] for t in created)
    assert all(t["join_code"] for t in created)
    # Repetir salta los que ya existen.
    again = h.ok(teacher.post(f"{teams_url}/bulk", json={"count": 13}, headers=CSRF), 201)
    assert [t["name"] for t in again] == ["Pareja 13"]
    h.error(teacher.post(f"{teams_url}/bulk", json={"count": 0}, headers=CSRF), 422, VALIDATION)

    # Equipo con integrantes iniciales: el docente no entra.
    team = h.ok(
        teacher.post(
            teams_url, json={"name": "Pareja Extra", "member_ids": [ids["Ana"]]}, headers=CSRF
        ),
        201,
    )
    assert _member_ids(team) == [ids["Ana"]]
    h.error(
        teacher.post(teams_url, json={"name": "pareja extra"}, headers=CSRF),
        CONFLICT,
        "team_name_taken",
    )
    taken = h.error(
        teacher.post(teams_url, json={"name": "Otra", "member_ids": [ids["Ana"]]}, headers=CSRF),
        CONFLICT,
        "already_in_team",
    )
    assert taken["details"]["members"] == [ids["Ana"]]
    too_big = h.error(
        teacher.post(
            teams_url,
            json={"name": "Trío", "member_ids": [ids["Beto"], ids["Carla"], ids["Dani"]]},
            headers=CSRF,
        ),
        422,
        VALIDATION,
    )
    assert "members" in too_big["details"]["fields"]
    me = h.ok(teacher.get(f"{API}/me"))["id"]
    h.error(
        teacher.post(teams_url, json={"name": "Profe", "member_ids": [me]}, headers=CSRF),
        422,
        VALIDATION,
    )

    # Mover: Ana pasa de «Pareja Extra» a «Pareja 1» en una sola operación.
    by_name = _teams_by_name(teacher, lab["id"])
    pair1 = by_name[PAIR_1]
    moved = h.ok(
        teacher.put(
            f"{API}/teams/{pair1['id']}/members", json=[ids["Ana"], ids["Beto"]], headers=CSRF
        )
    )
    assert _member_ids(moved) == [ids["Ana"], ids["Beto"]]
    assert _teams_by_name(teacher, lab["id"])["Pareja Extra"]["members"] == []

    # Renombrar.
    renamed = h.ok(
        teacher.patch(f"{API}/teams/{team['id']}", json={"name": "Pareja 14"}, headers=CSRF)
    )
    assert renamed["name"] == "Pareja 14"
    h.error(
        teacher.patch(f"{API}/teams/{team['id']}", json={"name": PAIR_1}, headers=CSRF),
        CONFLICT,
        "team_name_taken",
    )
    h.error(
        teacher.patch(f"{API}/teams/{team['id']}", json={"name": "  "}, headers=CSRF),
        422,
        VALIDATION,
    )

    # Reparto al azar: los 3 restantes caen en equipos no fijados con hueco (máx. 2).
    pair2 = by_name[PAIR_2]
    h.ok(teacher.post(f"{API}/teams/{pair2['id']}/lock", headers=CSRF))
    teams = h.ok(teacher.post(f"{teams_url}/auto-assign", headers=CSRF))
    assert h.ok(teacher.get(f"{teams_url}/unassigned")) == []
    assert all(len(t["members"]) <= 2 for t in teams)
    assert next(t for t in teams if t["id"] == pair2["id"])["members"] == []
    placed = {m for t in teams for m in _member_ids(t)}
    assert placed == set(ids.values())

    # Borrar un equipo vacío; sus integrantes (ninguno) quedan libres.
    deleted = teacher.delete(f"{API}/teams/{pair2['id']}", headers=CSRF)
    assert deleted.status_code == 204, deleted.text
    assert PAIR_2 not in _teams_by_name(teacher, lab["id"])
    h.error(teacher.delete(f"{API}/teams/{pair2['id']}", headers=CSRF), 404, NOT_FOUND)

    with engine.get_engine().connect() as conn:
        actions = set(
            conn.execute(
                sa.select(orm_base.AuditLogOrm.action).where(
                    orm_base.AuditLogOrm.aggregate_type == "team",
                    orm_base.AuditLogOrm.actor_id == me,
                )
            )
            .scalars()
            .all()
        )
    assert {"team_created", "team_renamed", "team_deleted", "team_members_set"} <= actions


def test_deleting_team_frees_members_but_not_with_submissions(env: e2e.Env) -> None:
    teacher, lab, ids, clients = _setup(env, ("Ana", "Beto"))
    teams_url = f"{API}/labs/{lab['id']}/teams"
    empty_ok = h.ok(
        teacher.post(teams_url, json={"name": PAIR_1, "member_ids": [ids["Ana"]]}, headers=CSRF),
        201,
    )
    deleted = teacher.delete(f"{API}/teams/{empty_ok['id']}", headers=CSRF)
    assert deleted.status_code == 204, deleted.text
    assert [p["id"] for p in h.ok(teacher.get(f"{teams_url}/unassigned"))] == [
        ids["Ana"],
        ids["Beto"],
    ]

    team = h.ok(
        teacher.post(
            teams_url,
            json={"name": PAIR_2, "member_ids": [ids["Ana"], ids["Beto"]]},
            headers=CSRF,
        ),
        201,
    )
    project = h.create_project(clients["Ana"])
    h.ok(h.submit(clients["Ana"], lab["id"], project["id"]), 201)
    h.error(
        teacher.delete(f"{API}/teams/{team['id']}", headers=CSRF), CONFLICT, "team_has_submissions"
    )
    # Mover a Beto fuera de un equipo con entregas está permitido; la entrega conserva su foto.
    h.ok(teacher.put(f"{API}/teams/{team['id']}/members", json=[ids["Ana"]], headers=CSRF))
    submission = h.ok(teacher.get(f"{API}/labs/{lab['id']}/submissions"))[0]
    assert {m["id"] for m in submission["members"]} == {ids["Ana"], ids["Beto"]}


def test_students_cannot_use_teacher_team_endpoints(env: e2e.Env) -> None:
    teacher, lab, ids, clients = _setup(env, ("Ana", "Beto"))
    ana = clients["Ana"]
    teams_url = f"{API}/labs/{lab['id']}/teams"
    team = h.ok(teacher.post(teams_url, json={"name": PAIR_1}, headers=CSRF), 201)

    h.error(
        ana.post(teams_url, json={"name": "Mía", "member_ids": [ids["Beto"]]}, headers=CSRF),
        403,
        FORBIDDEN,
    )
    h.error(ana.post(f"{teams_url}/bulk", json={"count": 2}, headers=CSRF), 403, FORBIDDEN)
    h.error(ana.get(f"{teams_url}/unassigned"), 403, FORBIDDEN)
    h.error(ana.post(f"{teams_url}/auto-assign", headers=CSRF), 403, FORBIDDEN)
    h.error(
        ana.patch(f"{API}/teams/{team['id']}", json={"name": "Hack"}, headers=CSRF), 403, FORBIDDEN
    )
    h.error(ana.delete(f"{API}/teams/{team['id']}", headers=CSRF), 403, FORBIDDEN)
    # El flujo del estudiante sigue igual: crea su equipo y entra.
    own = h.ok(ana.post(teams_url, json={"name": "Mía"}, headers=CSRF), 201)
    assert _member_ids(own) == [ids["Ana"]]
    # Un extraño al curso ni ve el lab.
    outsider = env.signup("x@example.com")
    h.error(outsider.get(f"{teams_url}/unassigned"), 404, NOT_FOUND)
    h.error(outsider.delete(f"{API}/teams/{team['id']}", headers=CSRF), 404, NOT_FOUND)


def test_teacher_endpoints_reject_individual_labs(env: e2e.Env) -> None:
    teacher = env.signup("docente@example.com")
    course = h.create_course(teacher)
    lab = h.create_lab(teacher, course["id"])
    url = f"{API}/labs/{lab['id']}/teams"
    h.error(teacher.post(url, json={"name": "A"}, headers=CSRF), CONFLICT, "not_team_lab")
    h.error(teacher.post(f"{url}/bulk", json={"count": 2}, headers=CSRF), CONFLICT, "not_team_lab")
