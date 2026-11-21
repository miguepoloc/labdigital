"""Sync SQLAlchemy engine/session factory — ARCHITECTURE.md §2/§8. One Lambda invocation
handles exactly one request, so async buys nothing here; NullPool outside local dev because
no pooled connection survives a Lambda freeze."""

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.commons.adapters import settings

_engine: sa.Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine() -> sa.Engine:
    global _engine
    if _engine is None:
        app_settings = settings.get_settings()
        poolclass = sa.pool.NullPool if not app_settings.is_local_or_test else None
        _engine = sa.create_engine(app_settings.postgres_uri, poolclass=poolclass)
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory
