import datetime
from urllib import parse

import jwt
import pytest
import time_machine

from backend.commons.adapters import authentication
from tests.e2e import conftest as e2e

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF


def _cookies(response: object) -> dict[str, str]:
    headers = response.headers.get_list("set-cookie")  # type: ignore[attr-defined]
    return {h.split("=", 1)[0]: h for h in headers}


def _attrs(header: str) -> set[str]:
    return {part.strip().lower() for part in header.split(";")[1:]}


def test_login_sets_cookies_with_exact_contract_flags(env: e2e.Env) -> None:
    client = env.make_client()
    client.post(
        f"{API}/auth/register",
        json={
            "email": "ada@example.com",
            "full_name": "Ada",
            "password": e2e.PASSWORD,
            "accept_data_policy": True,
        },
        headers=CSRF,
    )
    client.post(
        f"{API}/auth/verify-email", json={"token": env.last_token("ada@example.com")}, headers=CSRF
    )

    response = client.post(
        f"{API}/auth/login",
        json={"email": "ADA@example.com", "password": e2e.PASSWORD, "remember": True},
        headers=CSRF,
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "full_name", "role", "email_verified", "created_at"}
    assert body["email"] == "ada@example.com" and body["email_verified"] is True
    cookies = _cookies(response)
    access, refresh = _attrs(cookies["ld_access"]), _attrs(cookies["ld_refresh"])
    assert {"httponly", "secure", "samesite=lax", "path=/labdigital/", "max-age=900"} <= access
    assert {"httponly", "secure", "samesite=strict", "path=/labdigital/api/v1/auth/"} <= refresh
    max_age = next(a for a in refresh if a.startswith("max-age="))
    assert abs(int(max_age.split("=")[1]) - 30 * 86400) < 60
    refresh_value = cookies["ld_refresh"].split(";")[0].split("=", 1)[1]
    token_id, secret = refresh_value.split(".", 1)
    assert len(token_id) == 36 and len(secret) > 30


def test_remember_false_makes_refresh_a_session_cookie(env: e2e.Env) -> None:
    client = env.signup("ana@example.com", remember=False)
    response = client.post(f"{API}/auth/refresh", headers=CSRF)
    assert response.status_code == 204
    refresh = _attrs(_cookies(response)["ld_refresh"])
    assert not any(a.startswith(("max-age", "expires")) for a in refresh)


def test_access_expires_and_refresh_recovers(env: e2e.Env) -> None:
    client = env.signup("bob@example.com")
    assert client.get(f"{API}/me").status_code == 200
    with time_machine.travel(
        datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(minutes=16)
    ):
        # el navegador habría descartado la cookie (Max-Age=900); se reenvía igual para
        # comprobar que el servidor valida `exp` por su cuenta
        expired = client.get(f"{API}/me")
        assert expired.status_code == 401 and expired.json()["error"]["code"] == "unauthenticated"
        assert client.post(f"{API}/auth/refresh", headers=CSRF).status_code == 204
        assert client.get(f"{API}/me").status_code == 200


def test_refresh_rotates_and_reuse_revokes_family(env: e2e.Env) -> None:
    client = env.signup("eve@example.com")
    old_refresh = client.cookies.get("ld_refresh")
    assert client.post(f"{API}/auth/refresh", headers=CSRF).status_code == 204
    new_refresh = client.cookies.get("ld_refresh")
    assert new_refresh != old_refresh

    attacker = env.make_client()
    attacker.cookies.set(
        "ld_refresh", old_refresh, domain="testserver.local", path="/labdigital/api/v1/auth/"
    )
    reused = attacker.post(f"{API}/auth/refresh", headers=CSRF)
    assert reused.status_code == 401 and reused.json()["error"]["code"] == "unauthenticated"
    # la familia completa quedó revocada: el refresh legítimo tampoco sirve ya
    assert client.post(f"{API}/auth/refresh", headers=CSRF).status_code == 401


def test_logout_revokes_session_and_clears_cookies(env: e2e.Env) -> None:
    client = env.signup("lou@example.com")
    stolen = client.cookies.get("ld_refresh")
    response = client.post(f"{API}/auth/logout", headers=CSRF)
    assert response.status_code == 204
    cleared = _cookies(response)
    assert "max-age=0" in _attrs(cleared["ld_access"]) and "max-age=0" in _attrs(
        cleared["ld_refresh"]
    )
    assert client.get(f"{API}/me").status_code == 401
    other = env.make_client()
    other.cookies.set(
        "ld_refresh", stolen, domain="testserver.local", path="/labdigital/api/v1/auth/"
    )
    assert other.post(f"{API}/auth/refresh", headers=CSRF).status_code == 401


def test_reset_password_revokes_all_sessions(env: e2e.Env) -> None:
    laptop = env.signup("rita@example.com")
    phone = env.login("rita@example.com")
    anon = env.make_client()
    assert (
        anon.post(
            f"{API}/auth/forgot-password", json={"email": "rita@example.com"}, headers=CSRF
        ).status_code
        == 202
    )
    token = env.last_token("rita@example.com")
    assert (
        anon.post(
            f"{API}/auth/reset-password",
            json={"token": token, "password": "nueva-contrasena-1"},
            headers=CSRF,
        ).status_code
        == 204
    )
    for device in (laptop, phone):
        assert device.post(f"{API}/auth/refresh", headers=CSRF).status_code == 401
        assert device.get(f"{API}/me").status_code == 401  # `ver` del access ya no coincide
    assert (
        anon.post(
            f"{API}/auth/reset-password",
            json={"token": token, "password": "otra-contrasena-2"},
            headers=CSRF,
        ).json()["error"]["code"]
        == "token_invalid"
    )
    env.login("rita@example.com", "nueva-contrasena-1")


def test_responses_identical_for_unknown_email(env: e2e.Env) -> None:
    env.signup("known@example.com")
    client = env.make_client()
    for path, payload in [
        ("register", {"full_name": "X Y", "password": e2e.PASSWORD, "accept_data_policy": True}),
        ("forgot-password", {}),
        ("resend-verification", {}),
    ]:
        known = client.post(
            f"{API}/auth/{path}", json={**payload, "email": "known@example.com"}, headers=CSRF
        )
        unknown = client.post(
            f"{API}/auth/{path}", json={**payload, "email": "nadie@example.com"}, headers=CSRF
        )
        assert (
            (known.status_code, known.json())
            == (unknown.status_code, unknown.json())
            == (202, known.json())
        )
        assert (
            set(known.headers.get_list("set-cookie"))
            == set(unknown.headers.get_list("set-cookie"))
            == set()
        )


def test_login_errors_follow_contract(env: e2e.Env) -> None:
    client = env.make_client()
    client.post(
        f"{API}/auth/register",
        json={
            "email": "nov@example.com",
            "full_name": "Nov",
            "password": e2e.PASSWORD,
            "accept_data_policy": True,
        },
        headers=CSRF,
    )
    unverified = client.post(
        f"{API}/auth/login",
        json={"email": "nov@example.com", "password": e2e.PASSWORD},
        headers=CSRF,
    )
    assert (unverified.status_code, unverified.json()["error"]["code"]) == (
        403,
        "email_not_verified",
    )
    wrong = client.post(
        f"{API}/auth/login",
        json={"email": "nov@example.com", "password": "otra-contrasena"},
        headers=CSRF,
    )
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (401, "invalid_credentials")
    invalid = client.post(
        f"{API}/auth/register",
        json={
            "email": "x@example.com",
            "full_name": "Xavier",
            "password": "corta",
            "accept_data_policy": True,
        },
        headers=CSRF,
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert set(invalid.json()["error"]["details"]["fields"]) == {"password"}
    missing = client.post(f"{API}/auth/login", json={"email": "x@example.com"}, headers=CSRF)
    assert missing.status_code == 422 and missing.json()["error"]["details"]["fields"] == {
        "password": "Campo obligatorio."
    }


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": e2e.ORIGIN},
        {"X-Requested-With": "labdigital"},
        {"X-Requested-With": "labdigital", "Origin": "https://evil.example"},
        {"X-Requested-With": "otro", "Origin": e2e.ORIGIN},
    ],
)
def test_csrf_rejects_mutations_without_header_or_same_origin(
    env: e2e.Env, headers: dict[str, str]
) -> None:
    client = env.make_client()
    response = client.post(
        f"{API}/auth/login", json={"email": "a@example.com", "password": "x"}, headers=headers
    )
    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "csrf_rejected", "message": "Petición rechazada por protección CSRF."}
    }


def test_login_rate_limit_returns_429_with_retry_after(env: e2e.Env) -> None:
    client = env.make_client()
    body = {"email": "brute@example.com", "password": "no-es-esta-1"}
    statuses = [
        client.post(f"{API}/auth/login", json=body, headers=CSRF).status_code for _ in range(5)
    ]
    assert statuses == [401] * 5
    blocked = client.post(f"{API}/auth/login", json=body, headers=CSRF)
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60


def test_forgot_password_rate_limit(env: e2e.Env) -> None:
    client = env.make_client()
    for _ in range(3):
        assert (
            client.post(
                f"{API}/auth/forgot-password", json={"email": "f@example.com"}, headers=CSRF
            ).status_code
            == 202
        )
    assert (
        client.post(
            f"{API}/auth/forgot-password", json={"email": "f@example.com"}, headers=CSRF
        ).status_code
        == 429
    )


def test_auth_verify_for_nginx(env: e2e.Env) -> None:
    client = env.signup("jose@example.com", full_name="José Núñez")
    ok = client.get(f"{API}/auth/verify")
    assert ok.status_code == 204
    me = client.get(f"{API}/me").json()
    assert ok.headers["X-LabDigital-User"] == me["id"]
    assert ok.headers["X-LabDigital-Email"] == "jose@example.com"
    assert ok.headers["X-LabDigital-Name"] == "Jos%C3%A9%20N%C3%BA%C3%B1ez"
    assert parse.unquote(ok.headers["X-LabDigital-Name"]) == "José Núñez"
    assert ok.headers["X-LabDigital-Role"] == "user"

    assert env.make_client().get(f"{API}/auth/verify").status_code == 401
    forged = env.make_client()
    forged.cookies.set(
        "ld_access",
        client.cookies.get("ld_access")[:-4] + "AAAA",
        domain="testserver.local",
        path="/labdigital/",
    )
    assert forged.get(f"{API}/auth/verify").status_code == 401
    with time_machine.travel(
        datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(minutes=16)
    ):
        assert client.get(f"{API}/auth/verify").status_code == 401


def test_jwks_publishes_kid_and_verifies_access(env: e2e.Env) -> None:
    client = env.signup("mod@example.com")
    jwks = client.get(f"{API}/.well-known/jwks.json")
    assert jwks.status_code == 200
    (key,) = jwks.json()["keys"]
    assert (key["kid"], key["kty"], key["alg"], key["use"]) == ("ld-test", "RSA", "RS256", "sig")
    token = client.cookies.get("ld_access")
    assert jwt.get_unverified_header(token)["kid"] == "ld-test"
    public_key = jwt.PyJWK(key).key
    claims = jwt.decode(
        token, public_key, algorithms=["RS256"], audience="labdigital", issuer="labdigital"
    )
    assert set(claims) == {
        "iss",
        "aud",
        "sub",
        "sid",
        "role",
        "ver",
        "email",
        "name",
        "iat",
        "exp",
        "jti",
    }
    assert claims["exp"] - claims["iat"] == int(authentication.ACCESS_TOKEN_TTL.total_seconds())


def test_admin_emails_get_admin_role_on_verification(env: e2e.Env) -> None:
    client = env.signup("admin@example.com")
    assert client.get(f"{API}/me").json()["role"] == "admin"
    assert client.get(f"{API}/auth/verify").headers["X-LabDigital-Role"] == "admin"


def test_sessions_list_revoke_and_revoke_others(env: e2e.Env) -> None:
    first = env.signup("multi@example.com")
    second = env.login("multi@example.com")
    third = env.login("multi@example.com")
    listed = first.get(f"{API}/auth/sessions").json()
    assert len(listed) == 3 and sum(s["current"] for s in listed) == 1
    assert set(listed[0]) == {"id", "user_agent", "ip", "created_at", "last_used_at", "current"}

    second_id = next(s["id"] for s in second.get(f"{API}/auth/sessions").json() if s["current"])
    assert first.delete(f"{API}/auth/sessions/{second_id}", headers=CSRF).status_code == 204
    assert second.post(f"{API}/auth/refresh", headers=CSRF).status_code == 401

    assert third.post(f"{API}/auth/sessions/revoke-others", headers=CSRF).status_code == 204
    assert first.post(f"{API}/auth/refresh", headers=CSRF).status_code == 401
    assert [s["current"] for s in third.get(f"{API}/auth/sessions").json()] == [True]

    stranger = env.signup("stranger@example.com")
    assert stranger.delete(f"{API}/auth/sessions/{second_id}", headers=CSRF).status_code == 404


def test_me_update_and_change_password(env: e2e.Env) -> None:
    client = env.signup("pat@example.com")
    other_device = env.login("pat@example.com")
    patched = client.patch(f"{API}/me", json={"full_name": "  Pat   Smith "}, headers=CSRF)
    assert patched.status_code == 200 and patched.json()["full_name"] == "Pat Smith"
    assert set(patched.json()) == {
        "id",
        "email",
        "full_name",
        "role",
        "email_verified",
        "created_at",
    }

    wrong = client.post(
        f"{API}/me/password",
        json={"current": "no-es-la-actual", "new": "nueva-contrasena-1"},
        headers=CSRF,
    )
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (400, "invalid_current_password")

    changed = client.post(
        f"{API}/me/password",
        json={"current": e2e.PASSWORD, "new": "nueva-contrasena-1"},
        headers=CSRF,
    )
    assert changed.status_code == 204 and "ld_access" in _cookies(changed)
    assert client.get(f"{API}/me").status_code == 200  # la sesión actual sigue viva
    assert client.post(f"{API}/auth/refresh", headers=CSRF).status_code == 204
    assert other_device.post(f"{API}/auth/refresh", headers=CSRF).status_code == 401


def test_health_and_error_format(env: e2e.Env) -> None:
    client = env.make_client()
    assert client.get(f"{API}/health").json() == {"ok": True}
    assert client.get("/v1/health").json() == {"ok": True}  # nginx quitando el prefijo
    missing = client.get(f"{API}/no-existe")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
    unauth = client.get(f"{API}/me")
    assert unauth.status_code == 401 and unauth.json()["error"]["code"] == "unauthenticated"
