from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

# Postgres names every index and constraint for us, so migrations never depend on
# a hand-typed name. Composite indexes use column_0_N_label so they stay distinct.
POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "%(column_0_N_label)s_idx",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    # Guards against Postgres restarts and idle-connection reapers, which would
    # otherwise surface as a 500 on the first request to reuse a dead connection.
    pool_pre_ping=True,
    pool_recycle=1800,
    # Surface pool exhaustion as a fast failure rather than a 30s hang that
    # outlives gunicorn's worker timeout.
    pool_timeout=10,
)

# expire_on_commit=False is mandatory, not stylistic: the default expires every
# loaded attribute at commit, and ~9 routes read attributes off an object after
# committing it. Under async that expiry becomes a lazy refresh with no greenlet
# context — i.e. MissingGreenlet instead of a value.
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # Plain construction, never .begin(): .begin() would acquire a connection
    # eagerly, so routes that reject a request before touching the database
    # (401s, 422s) would still open one.
    async with AsyncSessionLocal() as db:
        try:
            yield db
        except Exception:
            # Leave no half-applied transaction on a connection returning to the
            # pool. No-op when nothing was ever begun, so 401s stay free.
            if db.in_transaction():
                await db.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_db)]
