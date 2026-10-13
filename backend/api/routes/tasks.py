"""
Background Tasks API route.

Provides endpoints to list background worker tasks and check status of asynchronous jobs:
- GET /api/v1/tasks
- GET /api/v1/tasks/{task_id}
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, status

from backend.worker.tasks import get_task_worker

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "",
    summary="List background tasks",
    description="List recent asynchronous background tasks and their execution status.",
)
async def list_background_tasks(
    limit: int = Query(default=20, ge=1, le=100, description="Max tasks to return"),
) -> List[Dict[str, Any]]:
    worker = get_task_worker()
    return worker.list_tasks(limit=limit)


@router.get(
    "/{task_id}",
    summary="Get background task status",
    description="Retrieve execution details and result status for a background task ID.",
)
async def get_background_task(task_id: str) -> Dict[str, Any]:
    worker = get_task_worker()
    task = worker.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background task '{task_id}' not found.",
        )
    return task.to_dict()
