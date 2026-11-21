"""Configuración común de tests.

- Entorno: claves RS256 generadas en cada ejecución (nada de credenciales en el repo),
  `COOKIE_SECURE=true`, origen público `https://testserver` (el de `TestClient`).
- Argon2 con parámetros mínimos para que la suite sea rápida (la política real se prueba
  aparte en los tests de `HashedPassword`).
- Postgres real vía testcontainers (sólo si algún test lo pide): contenedor `ld-test-pg-*`
  en un puerto efímero del host, sin Ryuk, borrado al terminar; esquema con
  `alembic upgrade head` (prueba también las migraciones).
"""

from collections.abc import Generator
import os
import secrets

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from alembic import command as alembic_command  # noqa: E402
from alembic import config as alembic_config  # noqa: E402
import argon2  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402

from backend.commons.adapters import engine, settings  # noqa: E402
from backend.identity.users.domain.model import value_objects as users_value_objects  # noqa: E402

PUBLIC_BASE_URL = "https://testserver/labdigital"
ADMIN_EMAIL = "admin@example.com"
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rsa_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem


_PRIVATE, _PUBLIC = _rsa_pair()
os.environ.update(
    {
        "APP_ENV": "test",
        "JWT_PRIVATE_KEY_PEM": _PRIVATE,
        "JWT_PUBLIC_KEY_PEM": _PUBLIC,
        "JWT_KID": "ld-test",
        "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        "ADMIN_EMAILS": f"{ADMIN_EMAIL}, otro.admin@example.com",
        "COOKIE_SECURE": "true",
        "MAIL_FROM": "LabDigital <no-responder@example.com>",
    }
)
settings.get_settings.cache_clear()

# Argon2 barato en tests (la suite hace cientos de hashes).
users_value_objects._HASHER = argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str]:
    from testcontainers.postgres import PostgresContainer  # noqa: PLC0415

    # Prefijo configurable para que varias ramas/agentes en el mismo host no se pisen.
    prefix = os.environ.get("LD_TEST_CONTAINER_PREFIX", "ld-test-pg")
    container = PostgresContainer("postgres:16-alpine", driver="psycopg").with_name(
        f"{prefix}-{secrets.token_hex(4)}"
    )
    with container as postgres:
        url = postgres.get_connection_url()
        os.environ["DATABASE_URL"] = url
        settings.get_settings.cache_clear()
        engine.reset()
        cfg = alembic_config.Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "migrations"))
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        cfg.attributes["configure_logger"] = False
        alembic_command.upgrade(cfg, "head")
        yield url
        engine.reset()


_TABLES = (
    "project_versions, projects, refresh_tokens, sessions, email_tokens, users, "
    "outbox_events, audit_log, rate_limits, idempotency_keys"
)


@pytest.fixture
def db(postgres_url: str) -> Generator[sa.Engine]:
    """BD limpia por test (TRUNCATE de todas las tablas)."""
    sa_engine = engine.get_engine()
    with sa_engine.begin() as connection:
        connection.execute(sa.text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    yield sa_engine
