"""Configuración única del proceso — ARCHITECTURE.md §14.1.

Una sola clase `Settings` (pydantic-settings) para todo LabDigital: la API (uvicorn) y el
worker del outbox leen exactamente las mismas variables de entorno, validadas una vez en
`get_settings()`. Nunca `os.environ[...]` disperso por los adaptadores.

Despliegue: Docker siempre encendido (no Lambda), así que no hay `_Settings` locales por
función: todo lo que algún proceso necesita vive aquí.
"""

import enum
import functools
from urllib import parse

import pydantic
import pydantic_settings


class Environment(enum.StrEnum):
    LOCAL = enum.auto()
    TEST = enum.auto()
    STAGING = enum.auto()
    PROD = enum.auto()


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Environment = Environment.LOCAL

    # Base de datos — una URL completa (`postgresql://` o `postgresql+psycopg://`).
    database_url: str = "postgresql+psycopg://labdigital:labdigital@localhost:5432/labdigital"
    db_pool_size: int = 5

    # Par RS256 (contrato §2). Obligatorios, sin valor por defecto: emitir o verificar tokens
    # con una clave equivocada es un incidente, no algo que deba "funcionar" en silencio.
    jwt_private_key_pem: str
    jwt_public_key_pem: str
    jwt_kid: str = "ld-1"
    # Rotación de claves: la clave pública anterior sigue publicada en el JWKS y aceptada
    # al verificar hasta que caduquen los access emitidos con ella (15 min).
    jwt_previous_public_key_pem: str = ""
    jwt_previous_kid: str = ""

    # Correo saliente (worker del outbox).
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = 20.0
    mail_from: str = "LabDigital GIDEAM <no-responder@mcda.tools>"

    public_base_url: str = "https://gideam.unimagdalena.edu.co/labdigital"
    # Lista separada por comas; se normaliza a minúsculas.
    admin_emails: str = ""
    cookie_secure: bool = True

    # Versión vigente de la política de protección de datos (Acuerdo Superior 17 de 2018,
    # Ley 1581/2012) que se registra junto a la fecha de aceptación en el registro.
    data_policy_version: str = "acuerdo-17-2018"

    # Archivos subidos (contenido direccionado por SHA-256; volumen `labdigital-blobs`).
    blob_dir: str = "/data/blobs"

    # Worker
    worker_poll_seconds: float = 5.0

    @pydantic.field_validator(
        "jwt_private_key_pem", "jwt_public_key_pem", "jwt_previous_public_key_pem"
    )
    @classmethod
    def _unescape_newlines(cls, value: str) -> str:
        """Permite PEM en una sola línea con `\\n` literales (cómodo en `.env`)."""
        return value.replace("\\n", "\n")

    @property
    def postgres_uri(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
        elif url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgres://")
        return url

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower() for item in self.admin_emails.split(",") if item.strip()
        )

    @property
    def public_origin(self) -> str:
        """`https://host[:puerto]` de `public_base_url` — lo que el navegador manda en
        `Origin` (CSRF, contrato §2)."""
        parsed = parse.urlsplit(self.public_base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def public_path_prefix(self) -> str:
        """`/labdigital` — base de las rutas de cookies (contrato §2)."""
        return parse.urlsplit(self.public_base_url).path.rstrip("/")


@functools.cache
def get_settings() -> Settings:
    """Único punto de instanciación (singleton cacheado). Los tests llaman
    `get_settings.cache_clear()` tras cambiar el entorno."""
    return Settings()  # campos obligatorios (claves JWT) vienen del entorno
