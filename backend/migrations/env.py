"""Alembic environment — ARCHITECTURE.md §18. One shared metadata object
(commons.adapters.orm_base.Base.metadata), autogenerate-only. Every subcontext's orm.py
must be imported here so its tables register onto Base.metadata before autogenerate runs
— listed explicitly on purpose, so a new subcontext can't be silently forgotten."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.commons.adapters import orm_base, settings
from backend.files.blobs.adapters import orm as blobs_orm  # noqa: F401
from backend.identity.sessions.adapters import orm as sessions_orm  # noqa: F401
from backend.identity.users.adapters import orm as users_orm  # noqa: F401
from backend.projects.projects.adapters import orm as projects_orm  # noqa: F401
from backend.teaching.courses.adapters import orm as courses_orm  # noqa: F401
from backend.teaching.labs.adapters import orm as labs_orm  # noqa: F401
from backend.teaching.submissions.adapters import orm as submissions_orm  # noqa: F401

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# La URL puede venir ya puesta por quien invoca (tests); si no, del Settings único.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option(
        "sqlalchemy.url", settings.get_settings().postgres_uri.replace("%", "%%")
    )
target_metadata = orm_base.Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
