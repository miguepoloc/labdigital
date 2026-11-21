import pytest

from tests.e2e import conftest as e2e
from tests.unit.backend.projects.projects import test_projects as unit_projects

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF


def _create(client: object, name: str = "Contador") -> dict:
    response = client.post(
        f"{API}/projects",
        json={"name": name, "module": "fpga", "content": unit_projects.content("a")},
        headers=CSRF,
    )  # type: ignore[attr-defined]
    assert response.status_code == 201, response.text
    return response.json()


def test_project_crud_versions_and_autosave(env: e2e.Env) -> None:
    client = env.signup("owner@example.com")
    project = _create(client)
    assert (
        project["current_version"]["n"] == 1
        and project["content"]["format"] == "basys3-sim-project"
    )
    pid = project["id"]

    saved = client.put(
        f"{API}/projects/{pid}/autosave",
        json={"content": unit_projects.content("b"), "base_version": 1},
        headers=CSRF,
    )
    assert saved.status_code == 200 and saved.json() == {
        "version_id": project["current_version"]["id"],
        "n": 1,
    }

    manual = client.post(
        f"{API}/projects/{pid}/versions", json={"label": "Antes de la entrega"}, headers=CSRF
    )
    assert manual.status_code == 201 and manual.json()["kind"] == "manual"
    after = client.put(
        f"{API}/projects/{pid}/autosave",
        json={"content": unit_projects.content("c"), "base_version": 1},
        headers=CSRF,
    )
    assert after.json()["n"] == 2

    conflict = client.put(
        f"{API}/projects/{pid}/autosave",
        json={"content": unit_projects.content("d"), "base_version": 1},
        headers=CSRF,
    )
    assert conflict.status_code == 409
    error = conflict.json()["error"]
    assert error["code"] == "version_conflict" and error["details"]["current_version"] == 2

    versions = client.get(f"{API}/projects/{pid}/versions").json()
    assert [v["n"] for v in versions] == [2, 1] and "content" not in versions[0]
    v1 = client.get(f"{API}/projects/{pid}/versions/{versions[1]['id']}").json()
    assert v1["content"]["files"][0]["text"] == "b"
    restored = client.post(
        f"{API}/projects/{pid}/versions/{versions[1]['id']}/restore", headers=CSRF
    )
    assert restored.status_code == 200 and restored.json()["current_version"]["n"] == 3

    assert (
        client.patch(f"{API}/projects/{pid}", json={"name": "Semáforo"}, headers=CSRF).json()[
            "name"
        ]
        == "Semáforo"
    )
    listed = client.get(f"{API}/projects", params={"module": "fpga"}).json()
    assert [p["id"] for p in listed] == [pid] and "content" not in listed[0]
    assert client.delete(f"{API}/projects/{pid}", headers=CSRF).status_code == 204
    assert client.get(f"{API}/projects/{pid}").status_code == 404
    assert client.get(f"{API}/projects").json() == []


def test_projects_are_private_to_their_owner(env: e2e.Env) -> None:
    owner = env.signup("o1@example.com")
    intruder = env.signup("o2@example.com")
    project = _create(owner)
    pid, vid = project["id"], project["current_version"]["id"]
    for method, path, body in [
        ("GET", f"/projects/{pid}", None),
        ("PATCH", f"/projects/{pid}", {"name": "mío"}),
        ("DELETE", f"/projects/{pid}", None),
        (
            "PUT",
            f"/projects/{pid}/autosave",
            {"content": unit_projects.content(), "base_version": 1},
        ),
        ("POST", f"/projects/{pid}/versions", {}),
        ("GET", f"/projects/{pid}/versions", None),
        ("GET", f"/projects/{pid}/versions/{vid}", None),
        ("POST", f"/projects/{pid}/versions/{vid}/restore", None),
    ]:
        response = intruder.request(method, f"{API}{path}", json=body, headers=CSRF)
        assert response.status_code == 404, (method, path, response.text)
        assert response.json()["error"]["code"] == "not_found"
    assert intruder.get(f"{API}/projects").json() == []
    assert env.make_client().get(f"{API}/projects/{pid}").status_code == 401
    assert owner.get(f"{API}/projects/{pid}").status_code == 200


def test_project_content_limits(env: e2e.Env) -> None:
    client = env.signup("big@example.com")
    wrong = client.post(
        f"{API}/projects",
        json={"name": "x", "module": "fpga", "content": {"format": "otro"}},
        headers=CSRF,
    )
    assert (
        wrong.status_code == 422 and "content.format" in wrong.json()["error"]["details"]["fields"]
    )
    big = client.post(
        f"{API}/projects",
        json={
            "name": "x",
            "module": "fpga",
            "content": unit_projects.content("a" * (2 * 1024 * 1024 + 10)),
        },
        headers=CSRF,
    )
    assert big.status_code == 413 and big.json()["error"]["code"] == "payload_too_large"
    huge = client.post(
        f"{API}/projects",
        content=b"{" + b" " * (3 * 1024 * 1024 + 1) + b"}",
        headers={**CSRF, "Content-Type": "application/json"},
    )
    assert huge.status_code == 413
