"""Admin: buscar, desactivar (revoca sesiones), activar, cambiar rol; todo auditado."""

import pytest
import sqlalchemy as sa

from backend.commons.adapters import engine, orm_base
from tests import conftest as root
from tests.e2e import conftest as e2e
from tests.e2e import teaching_helpers as h

pytestmark = pytest.mark.e2e

API, CSRF = e2e.API, e2e.CSRF


def test_admin_users_flow(env: e2e.Env) -> None:
    admin = env.signup(root.ADMIN_EMAIL, full_name="Admin")
    user = env.signup("pepa@example.com", full_name="Pepa Pig")
    env.signup("otro@example.com", full_name="Otro")

    h.error(user.get(f"{API}/admin/users"), 403, "forbidden")
    h.error(user.post(f"{API}/admin/users/x/deactivate", headers=CSRF), 403, "forbidden")
    found = h.ok(admin.get(f"{API}/admin/users", params={"q": "PEPA"}))
    assert [u["email"] for u in found] == ["pepa@example.com"]
    assert set(found[0]) == {
        "id", "email", "full_name", "role", "is_active", "email_verified", "created_at",
    }  # fmt: skip
    assert len(h.ok(admin.get(f"{API}/admin/users"))) == 3
    assert h.ok(admin.get(f"{API}/admin/users", params={"q": "%"})) == []  # comodín escapado
    uid = found[0]["id"]

    off = h.ok(admin.post(f"{API}/admin/users/{uid}/deactivate", headers=CSRF))
    assert off["is_active"] is False
    assert user.post(f"{API}/auth/refresh", headers=CSRF).status_code == 401  # sesiones revocadas
    login = env.make_client().post(
        f"{API}/auth/login",
        json={"email": "pepa@example.com", "password": e2e.PASSWORD, "remember": False},
        headers=CSRF,
    )
    h.error(login, 403, "account_inactive")
    assert h.ok(admin.post(f"{API}/admin/users/{uid}/activate", headers=CSRF))["is_active"] is True
    promoted = env.login("pepa@example.com")
    assert (
        h.ok(admin.post(f"{API}/admin/users/{uid}/role", json={"role": "admin"}, headers=CSRF))[
            "role"
        ]
        == "admin"
    )
    # Cambiar el rol revoca las sesiones: el refresh con el rol viejo ya no sirve.
    assert promoted.post(f"{API}/auth/refresh", headers=CSRF).status_code == 401
    h.error(
        admin.post(f"{API}/admin/users/{uid}/role", json={"role": "jefe"}, headers=CSRF),
        422,
        "validation_error",
    )
    me = h.ok(admin.get(f"{API}/me"))["id"]
    h.error(
        admin.post(f"{API}/admin/users/{me}/deactivate", headers=CSRF), 409, "cannot_modify_self"
    )
    h.error(
        admin.post(f"{API}/admin/users/{me}/role", json={"role": "user"}, headers=CSRF),
        409,
        "cannot_modify_self",
    )
    with engine.get_engine().connect() as conn:
        actions = (
            conn.execute(
                sa.select(orm_base.AuditLogOrm.action).where(
                    orm_base.AuditLogOrm.aggregate_id == uid,
                    orm_base.AuditLogOrm.actor_id == me,
                )
            )
            .scalars()
            .all()
        )
    assert {"deactivated", "activated", "role_changed"} <= set(actions)
