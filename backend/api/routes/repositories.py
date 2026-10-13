"""
Repository management endpoints.

All routes delegate to RepositoryService for business logic.
Routes are responsible only for:
- Parsing and validating HTTP input (via Pydantic schemas)
- Calling the correct service method
- Mapping domain exceptions to appropriate HTTP status codes
- Formatting the HTTP response
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.schemas.repository import (
    IndexingJobResponse,
    IndexTriggerResponse,
    RepositoryCreate,
    RepositoryListResponse,
    RepositoryResponse,
)
from backend.services.repository_service import (
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    RepositoryService,
)

router = APIRouter(prefix="/repositories", tags=["repositories"])


def _service(db: AsyncSession = Depends(get_db)) -> RepositoryService:
    """Dependency that constructs the RepositoryService with an injected DB session."""
    return RepositoryService(db)


# ─── POST /repositories ───────────────────────────────────────────────────────


@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new repository",
    description=(
        "Register a GitHub repository or local path. "
        "Indexing is not started automatically — call POST /repositories/{id}/index."
    ),
)
async def create_repository(
    payload: RepositoryCreate,
    svc: RepositoryService = Depends(_service),
) -> RepositoryResponse:
    try:
        repo = await svc.create_repository(payload)
        return RepositoryResponse.model_validate(repo)
    except RepositoryAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )


# ─── GET /repositories ────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=RepositoryListResponse,
    summary="List registered repositories",
)
async def list_repositories(
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Max records to return")] = 20,
    svc: RepositoryService = Depends(_service),
) -> RepositoryListResponse:
    repos, total = await svc.list_repositories(skip=skip, limit=limit)
    return RepositoryListResponse(
        items=[RepositoryResponse.model_validate(r) for r in repos],
        total=total,
        skip=skip,
        limit=limit,
    )


# ─── GET /repositories/{id} ───────────────────────────────────────────────────


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get a repository by ID",
)
async def get_repository(
    repository_id: uuid.UUID,
    svc: RepositoryService = Depends(_service),
) -> RepositoryResponse:
    try:
        repo = await svc.get_repository(repository_id)
        return RepositoryResponse.model_validate(repo)
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ─── DELETE /repositories/{id} ────────────────────────────────────────────────


@router.delete(
    "/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a repository",
    description="Deletes the repository record and all associated indexing jobs.",
)
async def delete_repository(
    repository_id: uuid.UUID,
    svc: RepositoryService = Depends(_service),
) -> None:
    try:
        await svc.delete_repository(repository_id)
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ─── POST /repositories/{id}/index ────────────────────────────────────────────


@router.post(
    "/{repository_id}/index",
    response_model=IndexTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger repository indexing",
    description=(
        "Creates an indexing job for the repository. "
        "Phase 1: records the job. "
        "Phase 2: will actually clone, parse, and embed the repository."
    ),
)
async def trigger_indexing(
    repository_id: uuid.UUID,
    svc: RepositoryService = Depends(_service),
) -> IndexTriggerResponse:
    try:
        job = await svc.trigger_indexing(repository_id)

        # Enqueue the background indexing pipeline task
        try:
            from backend.worker.queue_adapter import get_task_queue
            task_queue = get_task_queue()
            await task_queue.submit_indexing_job(str(repository_id))
        except Exception as exc:
            logger.warning("Could not submit indexing to task queue, falling back to direct worker: %s", exc)
            from backend.worker.tasks import get_task_worker
            from backend.database.connection import get_db_context
            async def _bg_index():
                async with get_db_context() as db:
                    bg_svc = RepositoryService(db)
                    await bg_svc.execute_indexing(repository_id, job.id)
            get_task_worker().submit("index_repository", _bg_index)

        return IndexTriggerResponse(
            job_id=job.id,
            repository_id=repository_id,
            message="Indexing job queued and started.",
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ─── GET /repositories/{id}/status ────────────────────────────────────────────


@router.get(
    "/{repository_id}/status",
    response_model=Optional[IndexingJobResponse],
    summary="Get the latest indexing job status",
    description=(
        "Returns the most recent indexing job for the repository, "
        "or null if indexing has never been triggered."
    ),
)
async def get_indexing_status(
    repository_id: uuid.UUID,
    svc: RepositoryService = Depends(_service),
) -> Optional[IndexingJobResponse]:
    try:
        job = await svc.get_indexing_status(repository_id)
        if job is None:
            return None
        return IndexingJobResponse.model_validate(job)
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ─── GET /repositories/{id}/status/stream ─────────────────────────────────────


@router.get(
    "/{repository_id}/status/stream",
    summary="Stream indexing status via Server-Sent Events",
    description="Streams real-time progress updates for the repository's indexing job using SSE.",
)
async def stream_indexing_status(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    async def event_generator() -> AsyncGenerator[str, None]:
        svc = RepositoryService(db)
        while True:
            try:
                job = await svc.get_indexing_status(repository_id)
                if job is None:
                    yield "data: null\n\n"
                    break

                job_resp = IndexingJobResponse.model_validate(job)
                yield f"data: {job_resp.model_dump_json()}\n\n"

                if job_resp.status in ("completed", "failed"):
                    break

                await asyncio.sleep(1.5)
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
