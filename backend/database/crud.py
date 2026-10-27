"""
CRUD (Create Read Update Delete) operations for all ORM models.

Rules enforced here:
- No business logic — that belongs in services/.
- All database interaction happens through an injected AsyncSession.
- Functions call `db.flush()` instead of `db.commit()` — callers manage transactions.
- Type hints use SQLAlchemy's Sequence for multi-row returns.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import (
    IndexingJob,
    IndexingJobStatus,
    Repository,
    RepositorySourceType,
    RepositoryStatus,
)
from backend.database.user_models import UserOwnedRepository


# ─── Repository ───────────────────────────────────────────────────────────────


async def create_repository(
    db: AsyncSession,
    *,
    name: str,
    url: str,
    source_type: RepositorySourceType,
    branch: Optional[str] = "main",
    description: Optional[str] = None,
    owner_id: Optional[uuid.UUID] = None,
) -> Repository:
    """Insert a new Repository row and optionally assign ownership. Caller must commit."""
    repo = Repository(
        name=name,
        url=url,
        source_type=source_type,
        branch=branch,
        description=description,
    )
    db.add(repo)
    await db.flush()
    await db.refresh(repo)

    # SEC-02: record ownership when a user_id is provided
    if owner_id is not None:
        ownership = UserOwnedRepository(
            user_id=owner_id,
            repository_id=repo.id,
        )
        db.add(ownership)
        await db.flush()

    return repo


async def get_repository(
    db: AsyncSession, repository_id: uuid.UUID
) -> Optional[Repository]:
    """Fetch a single repository by primary key. Returns None if not found."""
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    return result.scalar_one_or_none()


async def get_repository_by_url(
    db: AsyncSession, url: str
) -> Optional[Repository]:
    """Fetch a repository by its unique URL. Returns None if not found."""
    result = await db.execute(select(Repository).where(Repository.url == url))
    return result.scalar_one_or_none()


async def list_repositories(
    db: AsyncSession, *, skip: int = 0, limit: int = 50
) -> Sequence[Repository]:
    """Return a paginated list of repositories ordered by creation time (newest first)."""
    result = await db.execute(
        select(Repository)
        .order_by(Repository.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def count_repositories(db: AsyncSession) -> int:
    """Return the total number of repositories."""
    result = await db.execute(select(func.count()).select_from(Repository))
    return result.scalar_one()


# ─── User-scoped repository helpers (SEC-02) ──────────────────────────────────


async def list_repositories_for_user(
    db: AsyncSession,
    owner_id: uuid.UUID,
    *,
    skip: int = 0,
    limit: int = 50,
) -> Sequence[Repository]:
    """Return repositories owned by a specific user, newest first."""
    result = await db.execute(
        select(Repository)
        .join(
            UserOwnedRepository,
            UserOwnedRepository.repository_id == Repository.id,
        )
        .where(UserOwnedRepository.user_id == owner_id)
        .order_by(Repository.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def count_repositories_for_user(
    db: AsyncSession,
    owner_id: uuid.UUID,
) -> int:
    """Return the number of repositories owned by a specific user."""
    result = await db.execute(
        select(func.count())
        .select_from(UserOwnedRepository)
        .where(UserOwnedRepository.user_id == owner_id)
    )
    return result.scalar_one()


async def is_repository_owner(
    db: AsyncSession,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Return True if the given user owns the given repository."""
    result = await db.execute(
        select(UserOwnedRepository).where(
            UserOwnedRepository.repository_id == repository_id,
            UserOwnedRepository.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def update_repository_status(
    db: AsyncSession,
    repository_id: uuid.UUID,
    *,
    status: RepositoryStatus,
    error_message: Optional[str] = None,
    file_count: Optional[int] = None,
    chunk_count: Optional[int] = None,
    commit_hash: Optional[str] = None,
    branch: Optional[str] = None,
) -> Optional[Repository]:
    """Update repository status fields. Caller must commit the transaction."""
    values: dict = {"status": status}
    if error_message is not None:
        values["error_message"] = error_message
    if file_count is not None:
        values["file_count"] = file_count
    if chunk_count is not None:
        values["chunk_count"] = chunk_count
    if commit_hash is not None:
        values["commit_hash"] = commit_hash
    if branch is not None:
        values["branch"] = branch

    await db.execute(
        update(Repository).where(Repository.id == repository_id).values(**values)
    )
    return await get_repository(db, repository_id)


async def delete_repository(
    db: AsyncSession, repository_id: uuid.UUID
) -> bool:
    """
    Delete a repository and all its indexing jobs (cascade).
    Returns True if deleted, False if not found.
    """
    repo = await get_repository(db, repository_id)
    if repo is None:
        return False
    await db.delete(repo)
    await db.flush()
    return True


# ─── IndexingJob ──────────────────────────────────────────────────────────────


async def create_indexing_job(
    db: AsyncSession, *, repository_id: uuid.UUID
) -> IndexingJob:
    """Create a new pending indexing job. Caller must commit the transaction."""
    job = IndexingJob(repository_id=repository_id)
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


async def get_indexing_job(
    db: AsyncSession, job_id: uuid.UUID
) -> Optional[IndexingJob]:
    result = await db.execute(
        select(IndexingJob).where(IndexingJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def get_latest_indexing_job(
    db: AsyncSession, repository_id: uuid.UUID
) -> Optional[IndexingJob]:
    """Return the most recently created indexing job for a repository."""
    result = await db.execute(
        select(IndexingJob)
        .where(IndexingJob.repository_id == repository_id)
        .order_by(IndexingJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_indexing_jobs(
    db: AsyncSession, repository_id: uuid.UUID
) -> Sequence[IndexingJob]:
    """Return all indexing jobs for a repository, newest first."""
    result = await db.execute(
        select(IndexingJob)
        .where(IndexingJob.repository_id == repository_id)
        .order_by(IndexingJob.created_at.desc())
    )
    return result.scalars().all()


async def update_indexing_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    *,
    status: Optional[IndexingJobStatus] = None,
    progress: Optional[float] = None,
    current_step: Optional[str] = None,
    error_message: Optional[str] = None,
    files_processed: Optional[int] = None,
    files_total: Optional[int] = None,
    chunks_created: Optional[int] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> Optional[IndexingJob]:
    """Partially update an indexing job. Caller must commit the transaction."""
    values: dict = {}
    if status is not None:
        values["status"] = status
    if progress is not None:
        values["progress"] = progress
    if current_step is not None:
        values["current_step"] = current_step
    if error_message is not None:
        values["error_message"] = error_message
    if files_processed is not None:
        values["files_processed"] = files_processed
    if files_total is not None:
        values["files_total"] = files_total
    if chunks_created is not None:
        values["chunks_created"] = chunks_created
    if started_at is not None:
        values["started_at"] = started_at
    if completed_at is not None:
        values["completed_at"] = completed_at

    if values:
        await db.execute(
            update(IndexingJob).where(IndexingJob.id == job_id).values(**values)
        )
    return await get_indexing_job(db, job_id)
