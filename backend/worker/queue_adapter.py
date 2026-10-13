"""
REL-01 Part 2: Unified Task Queue Adapter.

Provides a single `TaskQueueAdapter` interface that transparently routes
background jobs to either:

  Mode A — Local (default, zero dependencies):
    Uses the existing in-process `AsyncTaskWorker` with asyncio.Queue.
    Works in development, testing, and single-container deployments.

  Mode B — Distributed (when REDIS_URL is configured):
    Uses Redis as a message broker via Celery.
    Supports horizontal scaling across multiple worker containers.
    Jobs survive process restarts because they are stored in Redis.

Selection logic (auto-detect):
  1. If REDIS_URL is set in the environment AND the `celery` and `redis`
     packages are installed → Mode B (Redis/Celery).
  2. Otherwise → Mode A (local AsyncTaskWorker).

This means you can switch from local to distributed by simply adding
REDIS_URL to your .env file — no code changes required anywhere.

Public API (same for both modes):
  adapter = get_task_queue()
  task_id = await adapter.submit_indexing_job(repository_id_str)
  info    = await adapter.get_task_info(task_id)   → TaskInfo
  listing = await adapter.list_tasks(limit=50)     → List[TaskInfo]

TaskInfo is a uniform dict:
  {
    "task_id": str,
    "name": str,
    "status": "pending"|"running"|"completed"|"failed",
    "metadata": dict,
    "error": str|None,
    "created_at": str,
    "mode": "local"|"redis",
  }
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── TaskInfo type alias ───────────────────────────────────────────────────────

TaskInfo = Dict[str, Any]


# ── Abstract base ─────────────────────────────────────────────────────────────


class BaseTaskQueue:
    """Abstract interface that both adapters implement."""

    mode: str = "base"

    async def submit_indexing_job(self, repository_id: str) -> str:
        """Enqueue a repository indexing job. Returns task_id."""
        raise NotImplementedError

    async def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """Return status information for a single task."""
        raise NotImplementedError

    async def list_tasks(self, limit: int = 50) -> List[TaskInfo]:
        """Return recent tasks sorted newest-first."""
        raise NotImplementedError


# ── Mode A: Local AsyncTaskWorker adapter ─────────────────────────────────────


class LocalTaskQueue(BaseTaskQueue):
    """
    In-process adapter wrapping the existing AsyncTaskWorker.

    Zero external dependencies — works offline, in tests, and single-process
    deployments. Task state is held in process memory.
    """

    mode = "local"

    async def submit_indexing_job(self, repository_id: str) -> str:
        from backend.worker.tasks import get_task_worker

        async def _index_coro():
            from backend.database.connection import get_db_context
            from backend.services.repository_service import RepositoryService
            async with get_db_context() as db:
                svc = RepositoryService(db)
                return await svc.execute_indexing(uuid.UUID(repository_id))

        worker = get_task_worker()
        task_id = worker.submit(
            name="index_repository",
            coro_fn=_index_coro,
            metadata={"repository_id": repository_id, "mode": self.mode},
            max_retries=3,
        )
        logger.info("LocalTaskQueue: submitted index_repository task=%s repo=%s", task_id, repository_id)
        return task_id

    async def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        from backend.worker.tasks import get_task_worker
        task = get_task_worker().get_task(task_id)
        if task is None:
            return None
        info = task.to_dict()
        info["mode"] = self.mode
        return info

    async def list_tasks(self, limit: int = 50) -> List[TaskInfo]:
        from backend.worker.tasks import get_task_worker
        tasks = get_task_worker().list_tasks(limit=limit)
        for t in tasks:
            t["mode"] = self.mode
        return tasks


# ── Mode B: Redis / Celery adapter ───────────────────────────────────────────


class RedisTaskQueue(BaseTaskQueue):
    """
    Distributed adapter that enqueues jobs via Celery → Redis broker.

    Jobs survive process restarts and can be consumed by worker containers
    across a Docker Swarm / Kubernetes cluster. State is stored in Redis
    and polled via Celery's AsyncResult API.
    """

    mode = "redis"

    def __init__(self) -> None:
        from backend.worker.celery_app import get_celery_app
        self._celery = get_celery_app()

    async def submit_indexing_job(self, repository_id: str) -> str:
        """
        Enqueue a repository indexing job to Redis.

        The Celery worker container will pick it up asynchronously.
        Returns a Celery task UUID (hex string without dashes).
        """
        result = self._celery.send_task(
            "backend.worker.celery_tasks.index_repository",
            args=[repository_id],
        )
        task_id = str(result.id)
        logger.info("RedisTaskQueue: enqueued index_repository task=%s repo=%s", task_id, repository_id)
        return task_id

    async def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """
        Query a Celery task's current state from the Redis result backend.
        """
        from celery.result import AsyncResult
        ar = AsyncResult(task_id, app=self._celery)
        celery_state = ar.state          # PENDING / STARTED / SUCCESS / FAILURE / RETRY

        status_map = {
            "PENDING": "pending",
            "STARTED": "running",
            "RETRY": "pending",
            "SUCCESS": "completed",
            "FAILURE": "failed",
            "REVOKED": "cancelled",
        }
        status = status_map.get(celery_state, "pending")

        error: Optional[str] = None
        if celery_state == "FAILURE":
            error = str(ar.result) if ar.result else "Unknown error"

        return {
            "task_id": task_id,
            "name": "index_repository",
            "status": status,
            "celery_state": celery_state,
            "metadata": {},
            "error": error,
            "result": str(ar.result) if celery_state == "SUCCESS" else None,
            "created_at": None,     # Celery does not expose submission time in result backend
            "mode": self.mode,
        }

    async def list_tasks(self, limit: int = 50) -> List[TaskInfo]:
        """
        Note: Celery does not natively support listing all queued tasks.
        This returns an empty list unless you integrate Flower or a custom
        result store. Callers should query individual task IDs instead.
        """
        logger.debug("RedisTaskQueue.list_tasks: full listing not available without Flower")
        return []


# ── Factory / singleton ───────────────────────────────────────────────────────

_queue_instance: Optional[BaseTaskQueue] = None


def _build_queue() -> BaseTaskQueue:
    """
    Detect which mode to use based on environment configuration.

    Selection rules:
      1. REDIS_URL set + celery installed + redis installed → RedisTaskQueue
      2. Otherwise → LocalTaskQueue
    """
    from backend.config.settings import settings

    if not settings.REDIS_URL:
        logger.info("TaskQueue: REDIS_URL not set — using local in-process queue")
        return LocalTaskQueue()

    # Check that optional dependencies are installed
    try:
        import celery  # noqa: F401
        import redis    # noqa: F401
    except ImportError as exc:
        logger.warning(
            "TaskQueue: REDIS_URL is set but required packages are missing (%s). "
            "Falling back to local in-process queue. "
            "Install with: pip install 'celery[redis]>=5.4.0' redis>=5.1.0",
            exc,
        )
        return LocalTaskQueue()

    try:
        queue = RedisTaskQueue()
        logger.info("TaskQueue: Redis/Celery distributed queue active (broker=%s)", settings.REDIS_URL[:30] + "…")
        return queue
    except Exception as exc:
        logger.warning(
            "TaskQueue: Failed to initialise Redis queue (%s). "
            "Falling back to local in-process queue.",
            exc,
        )
        return LocalTaskQueue()


def get_task_queue() -> BaseTaskQueue:
    """
    Return the process-wide task queue singleton.

    Automatically selects LocalTaskQueue or RedisTaskQueue based on
    whether REDIS_URL is configured and optional packages are installed.
    """
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = _build_queue()
    return _queue_instance


def reset_task_queue() -> None:
    """
    Reset the singleton (used in tests to switch modes without restart).
    """
    global _queue_instance
    _queue_instance = None
