"""
Database connection management — async SQLAlchemy engine and session factory.

Design decisions:
- asyncpg driver: faster than psycopg2 for async workloads, no GIL issues.
- Module-level singletons: one engine + one session factory for the process lifetime.
- `dispose_engine()` must be called on shutdown to close all pooled connections.
- In testing, these singletons are NOT used; tests provide their own SQLite engine
  via FastAPI dependency override.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config.settings import settings
from backend.database.models import Base
import backend.database.user_models  # noqa: F401  — registers User/UserOwnedRepository in Base.metadata

logger = logging.getLogger(__name__)

# Module-level singletons — initialized lazily on first use.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> AsyncEngine:
    """Instantiate the async SQLAlchemy engine with connection pool settings."""
    url = settings.async_database_url
    if "sqlite" in url:
        return create_async_engine(
            url,
            echo=settings.is_development,
        )
    return create_async_engine(
        url,
        echo=settings.is_development,   # Log SQL in dev; never in prod
        pool_size=10,
        max_overflow=20,
        pool_timeout=30.0,              # Bounded wait for pool connection (REL-06)
        pool_pre_ping=True,             # Detect stale connections before use
        pool_recycle=3600,              # Recycle connections every hour
    )


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = _create_engine()
        logger.info("Database engine created: url=%s", settings.DATABASE_URL[:40] + "…")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,     # Keep objects usable after commit
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions outside FastAPI dependency injection.

    Usage:
        async with get_db_context() as db:
            result = await db.execute(select(Repository))

    Commits on success, rolls back on any exception.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """
    Create all ORM-defined tables using CREATE TABLE IF NOT EXISTS.

    Used during development startup. In production, Alembic manages schema
    migrations (planned for Phase 8).
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured.")


async def dispose_engine() -> None:
    """
    Dispose the database engine and close all pooled connections.

    Must be called during application shutdown to prevent resource leaks.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine disposed.")
