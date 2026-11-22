"""Engine/sesiones SQLAlchemy síncronos — ARCHITECTURE.md §2/§8.

LabDigital corre como proceso siempre encendido (uvicorn en Docker), así que se usa el pool
de conexiones normal de SQLAlchemy (`QueuePool`) con `pool_pre_ping` para sobrevivir a
reinicios de Postgres. Los endpoints FastAPI son `def` (síncronos): Starlette los ejecuta en
su pool de hilos, una sesión por petición vía `UnitOfWork`."""

import sqlalchemy as sa
from sqlalchemy import orm

from backend.commons.adapters import settings

_engine: sa.Engine | None = None
_session_factory: orm.sessionmaker[orm.Session] | None = None


def get_engine() -> sa.Engine:
    global _engine
    if _engine is None:
        app_settings = settings.get_settings()
        _engine = sa.create_engine(
            app_settings.postgres_uri,
            pool_size=app_settings.db_pool_size,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> orm.sessionmaker[orm.Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = orm.sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def reset() -> None:
    """Descarta engine y fábrica cacheados (tests que cambian `DATABASE_URL`)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
