"""
FastAPI dependency injection helpers.

These are the reusable dependencies that routes declare via `Depends(...)`.
Keeping them here avoids circular imports and makes testing easy via
`app.dependency_overrides`.
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a database session for a single HTTP request.

    - Commits on success.
    - Rolls back on any unhandled exception.
    - The session is always closed after the request, returning the
      connection to the pool.

    Override in tests:
        app.dependency_overrides[get_db] = lambda: test_session_generator()
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
