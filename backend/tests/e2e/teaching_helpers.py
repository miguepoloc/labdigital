"""Atajos para los e2e de cursos/labs/entregas: crean el escenario por la API real."""

import datetime
from typing import Any

from fastapi import testclient

from tests.e2e import conftest as e2e
from tests.unit.backend.projects.projects import test_projects as unit_projects

API, CSRF = e2e.API, e2e.CSRF

PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
BIT = b"\x00\x09\x0f\xf0\x0f\xf0\x0f\xf0\x0f\xf0\x00\x00\x01a" + b"\xff" * 64


def iso(delta: datetime.timedelta) -> str:
    return (datetime.datetime.now(tz=datetime.UTC) + delta).isoformat()


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code, body
    return body


def create_course(teacher: testclient.TestClient, name: str = "Diseño Digital") -> dict[str, Any]:
    return ok(
        teacher.post(
            f"{API}/courses",
            json={"name": name, "period": "2027-I", "description": "FPGA"},
            headers=CSRF,
        ),
        201,
    )


def enroll(
    teacher: testclient.TestClient, student: testclient.TestClient, course: dict[str, Any]
) -> str:
    """Estudiante pide entrar con el código y el docente aprueba. Devuelve su user id."""
    joined = ok(
        student.post(f"{API}/courses/join", json={"code": course["join_code"]}, headers=CSRF)
    )
    assert joined["my_status"] == "pending"
    me = ok(student.get(f"{API}/me"))
    ok(teacher.post(f"{API}/courses/{course['id']}/members/{me['id']}/approve", headers=CSRF))
    return str(me["id"])


def lab_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Lab 1: semáforo",
        "statement_md": "# Semáforo\n<script>alert(1)</script>",
        "module": "fpga",
        "deadline_policy": "none",
        "team_mode": "individual",
        "grade_scale": {"type": "numeric", "min": 0, "max": 5, "decimals": 1, "pass_mark": 3},
        "allow_resubmission": False,
    }
    body.update(overrides)
    return body


def create_lab(
    teacher: testclient.TestClient, course_id: str, *, publish: bool = True, **overrides: Any
) -> dict[str, Any]:
    lab = ok(
        teacher.post(f"{API}/courses/{course_id}/labs", json=lab_body(**overrides), headers=CSRF),
        201,
    )
    if publish:
        lab = ok(teacher.post(f"{API}/labs/{lab['id']}/publish", headers=CSRF))
    return dict(lab)


def create_project(client: testclient.TestClient, text: str = "v1") -> dict[str, Any]:
    return ok(
        client.post(
            f"{API}/projects",
            json={"name": "Semáforo", "module": "fpga", "content": unit_projects.content(text)},
            headers=CSRF,
        ),
        201,
    )


def autosave(client: testclient.TestClient, project_id: str, text: str) -> dict[str, Any]:
    current = ok(client.get(f"{API}/projects/{project_id}"))
    return dict(
        ok(
            client.put(
                f"{API}/projects/{project_id}/autosave",
                json={
                    "content": unit_projects.content(text),
                    "base_version": current["current_version_n"],
                    "base_revision": current["revision"],
                },
                headers=CSRF,
            )
        )
    )


def upload(client: testclient.TestClient, name: str, data: bytes, kind: str = "attachment") -> Any:
    return client.post(
        f"{API}/files",
        files={"file": (name, data, "application/octet-stream")},
        data={"kind": kind},
        headers=CSRF,
    )


def submit(
    client: testclient.TestClient,
    lab_id: str,
    project_id: str,
    *,
    file_ids: list[str] | None = None,
    version_id: str | None = None,
) -> Any:
    body: dict[str, Any] = {"project_id": project_id, "file_ids": file_ids or []}
    if version_id is not None:
        body["version_id"] = version_id
    return client.post(f"{API}/labs/{lab_id}/submissions", json=body, headers=CSRF)


def review(teacher: testclient.TestClient, submission_id: str, **body: Any) -> Any:
    return teacher.post(f"{API}/submissions/{submission_id}/reviews", json=body, headers=CSRF)
