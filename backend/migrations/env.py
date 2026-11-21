"""Alembic environment — ARCHITECTURE.md §18. One shared metadata object
(commons.adapters.orm_base.Base.metadata), autogenerate-only. Every subcontext's orm.py
must be imported here so its tables register onto Base.metadata before autogenerate runs
— easy to forget when adding a new subcontext, which is exactly why they're all listed
explicitly below instead of relying on import side effects elsewhere."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.commerce.orders.adapters import orm as orders_orm  # noqa: F401
from backend.commerce.stock.adapters import orm as stock_orm  # noqa: F401
from backend.commons.adapters import orm_base, settings
from backend.identity.users.adapters import orm as users_orm  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.get_postgres_uri())
target_metadata = orm_base.Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.get_postgres_uri(),
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
