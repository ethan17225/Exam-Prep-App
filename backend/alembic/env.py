import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Must be imported before target_metadata is read: importing only `database`
# leaves Base.metadata empty and autogenerate proposes dropping every table.
import src.models  # noqa: F401
from alembic import context
from src.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise SystemExit("DATABASE_URL is not set")
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render SQL without a database (`alembic upgrade head --sql`).

    Unaffected by the async engine below — the dialect resolves from the URL
    alone — so this stays a complete verification path with no Postgres running.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # Without this, a server_default declared on a model but absent from a
        # migration is silent drift — which had already happened once.
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        # NullPool: a pooled connection outliving asyncio.run's event loop
        # raises at interpreter shutdown.
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        # The greenlet bridge — every op.* inside runs against a sync facade, so
        # revision files need no async awareness at all.
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
