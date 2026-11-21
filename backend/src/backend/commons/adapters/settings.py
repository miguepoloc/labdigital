"""Environment-driven settings — ARCHITECTURE.md §2/§3/§14.1. `pydantic_settings.BaseSettings`,
not hand-rolled `os.environ` reads: `pydantic-settings` was already a declared dependency
(`pyproject.toml`), unused until now, and every field it validates once at construction —
a malformed `DB_PORT` fails loudly the first time `get_settings()` is called, not on the
first query that happens to touch it. Verified against `sona-sso-backend`'s real
`commons/settings.py`, the directly comparable precedent (same FastAPI+SQLAlchemy+Lambda
stack, not bold's heavier SSM-backed version this template doesn't need).

`Settings` (this class) holds only what's genuinely cross-cutting — used by `commons/`
itself or by more than one product: DB connection, RS256 keys (identity issues, every
product verifies, §9.3), `internal_api_key` (both identity's `_dependencies.py` and
commerce's `user_profile_adapter.py` need the same value, §9.2). Everything with exactly one
consumer — `pricing_adapter.HttpPricingAdapter`'s base URL, `outbox_relay.py`'s own SNS
topic ARN — is NOT here. It's a local `_Settings(settings.Settings)` subclass declared right
in the file that needs it, module-level `_SETTINGS = _Settings()` singleton, the exact shape
bold uses well over a thousand times across the real codebase (e.g.
`accounting/loans/revolving/adapters/biometric_identity_provider.py`, CLAUDE.md's own
"Settings: module-level `_Settings(commons_settings.Settings)` singleton `_SETTINGS`" rule).

This isn't just naming hygiene: an earlier draft of this template put `pricing_service_base_url`
and `identity_internal_api_base_url` on this shared class, which meant EVERY Lambda in this
system — including identity's, which never touches pricing — had to have
`PRICING_SERVICE_BASE_URL` set in its own environment just for `Settings()` to construct
(every entrypoint calls `unit_of_work.build()`, which reads this same class). A required
field with exactly one real consumer belongs on that consumer's own local `_Settings`, not on
the one every Lambda process is forced to satisfy.

Still exactly one settings vocabulary per concern, never a scattered `os.environ[...]` call
in whatever adapter happens to need it — an earlier draft of this template had exactly that
too: `pricing_adapter.py`, `user_profile_adapter.py`, and
`identity/entrypoints/web/_dependencies.py` each read `os.environ[...]` directly,
`INTERNAL_API_KEY` duplicated across two of them with no single place declaring it required.
`commons.adapters.logs.py`'s own `os.environ.get("AWS_LAMBDA_FUNCTION_NAME", ...)` is the one
deliberate exception, matching bold's identical `commons/cloud/logs.py`: a platform-injected
runtime identifier, not application configuration — it was never a candidate for `Settings`
to begin with, in either codebase."""

import enum

import pydantic_settings


class Environment(enum.StrEnum):
    LOCAL = enum.auto()
    TEST = enum.auto()
    DEV = enum.auto()
    STAGING = enum.auto()
    PROD = enum.auto()


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Environment = Environment.LOCAL

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "backend"
    db_password: str = "backend"
    db_name: str = "backend"

    # RS256 key pair (ARCHITECTURE.md §9.3) — required, no default: a Lambda that issues or
    # verifies tokens without these misconfigured is a security incident, not a place for a
    # silently-wrong fallback.
    jwt_private_key_pem: str
    jwt_public_key_pem: str

    # Service-to-service auth for entrypoints/web/internal.py (§9.2) — two consumers
    # (identity's own `_dependencies.py` and commerce's `user_profile_adapter.py`), a real
    # cross-product concern, unlike `pricing_service_base_url`/`sns_topic_arn_*` below.
    internal_api_key: str

    @property
    def postgres_uri(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def is_local_or_test(self) -> bool:
        return self.app_env in (Environment.LOCAL, Environment.TEST)

    @property
    def use_fake_external_adapters(self) -> bool:
        """Everything except PROD runs against `Fake<Capability>` adapters for external
        systems this codebase doesn't own (`adapters/adapter_factory.py`) — the same role
        bold's `OU` env var / `context.in_development_ou()` plays for `deposit/breb`'s real
        adapters, decided here off `app_env` instead of a second, separate env var. A
        deliberate simplification from bold's 3-value `OUExecutionEnv`: this codebase's
        `Environment` already has LOCAL/TEST/DEV/STAGING/PROD, so "not PROD" says exactly
        what bold's `in_development_ou()` (DEV-prefixed OU) plus LOCAL/TEST already running
        against fakes by construction would otherwise take two checks to say."""
        return self.app_env is not Environment.PROD


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    """Single instantiation point — cached module-level singleton, the same caching shape
    `commons.adapters.engine`'s own `_engine`/`_session_factory` already use."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()
    return _SETTINGS
