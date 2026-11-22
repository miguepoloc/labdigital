"""Regresiones de la revisión de seguridad de identidad (puntos 2, 3 y 4)."""

from urllib import parse

import pytest

from backend.commons.adapters import authentication
from tests import conftest as root
from tests.e2e import conftest as e2e
from tests.e2e import teaching_helpers as h

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF


def _steal_access(client: object) -> object:
    """Otro navegador con SÓLO la cookie de access copiada."""
    return client.cookies.get("ld_access")  # type: ignore[attr-defined]


def _thief(env: e2e.Env, access: object) -> object:
    thief = env.make_client()
    thief.cookies.set("ld_access", access, domain="testserver.local", path="/labdigital/")
    return thief


SENSITIVE = [
    ("GET", "/projects", None),
    ("POST", "/projects", {"name": "x", "module": "fpga", "content": {"format": "x"}}),
    ("GET", "/courses", None),
    ("POST", "/courses", {"name": "x", "period": "x"}),
    ("GET", "/auth/sessions", None),
    ("PATCH", "/me", {"full_name": "Robado"}),
    ("POST", "/files", None),
]


def _assert_dead(thief: object) -> None:
    for method, path, body in SENSITIVE:
        response = thief.request(method, f"{API}{path}", json=body, headers=CSRF)  # type: ignore[attr-defined]
        assert response.status_code == 401, (method, path, response.text)
        assert response.json()["error"]["code"] == "unauthenticated"


def test_stolen_access_dies_with_logout_but_verify_stays_db_free(env: e2e.Env) -> None:
    victim = env.signup("v@example.com")
    access = _steal_access(victim)
    thief = _thief(env, access)
    assert thief.get(f"{API}/projects").status_code == 200  # type: ignore[attr-defined]
    assert victim.post(f"{API}/auth/logout", headers=CSRF).status_code == 204
    _assert_dead(thief)
    # Contrato §3: /auth/verify no consulta la BD (el access caduca solo en ≤15 min).
    assert thief.get(f"{API}/auth/verify").status_code == 204  # type: ignore[attr-defined]


def test_stolen_access_dies_with_session_revocation_and_password_change(env: e2e.Env) -> None:
    victim = env.signup("v@example.com")
    thief = _thief(env, _steal_access(victim))
    other_device = env.login("v@example.com")
    sessions = h.ok(other_device.get(f"{API}/auth/sessions"))
    stolen_sid = next(s["id"] for s in sessions if not s["current"])
    assert other_device.delete(f"{API}/auth/sessions/{stolen_sid}", headers=CSRF).status_code == 204
    _assert_dead(thief)

    # Cambio de contraseña: el access viejo de otra sesión tampoco sirve (otra `ver`).
    third = env.login("v@example.com")
    thief2 = _thief(env, _steal_access(third))
    changed = other_device.post(
        f"{API}/me/password",
        json={"current": e2e.PASSWORD, "new": "otra-clave-larga-9"},
        headers=CSRF,
    )
    assert changed.status_code == 204
    _assert_dead(thief2)
    assert other_device.get(f"{API}/projects").status_code == 200  # la sesión actual sigue


def test_stolen_access_dies_when_admin_deactivates_the_user(env: e2e.Env) -> None:
    admin = env.signup(root.ADMIN_EMAIL)
    victim = env.signup("v@example.com")
    thief = _thief(env, _steal_access(victim))
    uid = h.ok(victim.get(f"{API}/me"))["id"]
    h.ok(admin.post(f"{API}/admin/users/{uid}/deactivate", headers=CSRF))
    _assert_dead(thief)


def test_verify_url_encodes_non_latin1_email(env: e2e.Env) -> None:
    token = authentication.issue_access_token(
        user_id="0190d1f0-0000-7000-8000-000000000001",
        session_id="0190d1f0-0000-7000-8000-000000000002",
        role="user",
        credentials_version=1,
        email="josé.ñandú@example.com",
        name="José Ñandú",
    )
    client = env.make_client()
    client.cookies.set("ld_access", token, domain="testserver.local", path="/labdigital/")
    response = client.get(f"{API}/auth/verify")
    assert response.status_code == 204
    assert parse.unquote(response.headers["X-LabDigital-Email"]) == "josé.ñandú@example.com"
    assert parse.unquote(response.headers["X-LabDigital-Name"]) == "José Ñandú"
    plain = authentication.issue_access_token(
        user_id="0190d1f0-0000-7000-8000-000000000001",
        session_id="0190d1f0-0000-7000-8000-000000000002",
        role="user",
        credentials_version=1,
        email="ana+lab@example.com",
        name="Ana",
    )
    client.cookies.set("ld_access", plain, domain="testserver.local", path="/labdigital/")
    assert client.get(f"{API}/auth/verify").headers["X-LabDigital-Email"] == "ana+lab@example.com"


@pytest.mark.parametrize(
    "origin",
    [
        "http://testserver",  # mismo host, otro esquema
        "https://testserver:8443",  # otro puerto
        "https://evil.example",
        "https://testserver.evil.example",
        "https://testserver/ruta",
        "null",
    ],
)
def test_csrf_requires_the_exact_public_origin(env: e2e.Env, origin: str) -> None:
    client = env.make_client()
    response = client.post(
        f"{API}/auth/forgot-password",
        json={"email": "a@example.com"},
        headers={"X-Requested-With": "labdigital", "Origin": origin},
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_rejected"
    ok = client.post(
        f"{API}/auth/forgot-password",
        json={"email": "a@example.com"},
        headers={"X-Requested-With": "labdigital", "Origin": "https://TESTSERVER"},
    )
    assert ok.status_code == 202
