"""
FastAPI dependency injection helpers.

These are the reusable dependencies that routes declare via `Depends(...)`.
Keeping them here avoids circular imports and makes testing easy via
`app.dependency_overrides`.
"""
from __future__ import annotations

from typing import AsyncGenerator
import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import crud
from backend.database.connection import get_session_factory
from backend.database.models import Repository
from backend.security.dependencies import CurrentUser, get_current_user, require_repo_owner


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


async def get_valid_repository(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Repository:
    """
    FastAPI dependency: fetch and validate repository existence and tenant access.

    Raises:
        HTTP 404: If the repository does not exist.
        HTTP 403: If the current user does not have ownership access.
    """
    repo = await crud.get_repository(db, repository_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repository_id} not found.",
        )
    await require_repo_owner(repository_id, current_user, db)
    return repo
