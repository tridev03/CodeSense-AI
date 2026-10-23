"""
Test configuration and fixtures for the backend test suite.

Architecture decisions:
- Tests use an in-memory SQLite database (via aiosqlite) instead of PostgreSQL.
  This means tests have zero infrastructure requirements and run fast.
- The same SQLAlchemy ORM layer is exercised; only the driver changes.
- The FastAPI `get_db` dependency is overridden to yield the test session.
- Each test gets a fresh in-memory database (scope="function") for perfect isolation.
- The app lifespan is triggered but guarded by ENVIRONMENT=testing to skip
  the production PostgreSQL connection.

Environment variables are set BEFORE any application imports so that
Pydantic Settings initializes with test values.
"""
from __future__ import annotations

import os

# ── Set test environment variables BEFORE importing anything from the app ──
# This ensures pydantic-settings picks up these values on first import.
os.environ["ENVIRONMENT"] = "testing"
os.environ["GIT_PYTHON_REFRESH"] = "0"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "testing-secret-key-at-least-32-characters-long-for-testing"

# ── Application imports (after env vars are set) ───────────────────────────
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api.dependencies import get_db
from backend.database.models import Base
from backend.main import app

# ─── In-memory SQLite engine per test function ────────────────────────────────

_SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    """
    Create a fresh in-memory SQLite database for each test.

    Tables are created from the ORM metadata and dropped when the engine is
    disposed at the end of the test.
    """
    engine = create_async_engine(_SQLITE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a SQLAlchemy AsyncSession bound to the test SQLite engine.

    The session is rolled back after each test to undo any commits made by
    the service layer, ensuring isolation even within a single test.
    """
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client with the database dependency overridden.

    The `get_db` dependency is replaced with a generator that yields
    the test SQLite session, so all routes operate on the test database.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
