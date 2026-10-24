"""
Background Tasks API route.

Provides endpoints to list background worker tasks and check status of asynchronous jobs:
- GET /api/v1/tasks
- GET /api/v1/tasks/{task_id}
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.security.dependencies import CurrentUser, get_current_user
from backend.worker.tasks import get_task_worker

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "",
    summary="List background tasks",
    description="List recent asynchronous background tasks and their execution status.",
)
async def list_background_tasks(
    limit: int = Query(default=20, ge=1, le=100, description="Max tasks to return"),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    worker = get_task_worker()
    all_tasks = worker.list_tasks(limit=limit)
    if current_user.is_superuser:
        return all_tasks
    user_id_str = str(current_user.user_id)
    return [
        t
        for t in all_tasks
        if t.get("metadata", {}).get("owner_id") == user_id_str
        or not t.get("metadata", {}).get("owner_id")
    ]


@router.get(
    "/{task_id}",
    summary="Get background task status",
    description="Retrieve execution details and result status for a background task ID.",
)
async def get_background_task(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    worker = get_task_worker()
    task = worker.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background task '{task_id}' not found.",
        )
    task_dict = task.to_dict()
    task_owner = task_dict.get("metadata", {}).get("owner_id")
    if not current_user.is_superuser and task_owner and task_owner != str(current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this task.",
        )
    return task_dict
