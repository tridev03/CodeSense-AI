"""
Asynchronous background task worker and job manager.

Manages execution of long-running operations:
- Repository cloning & AST indexing jobs
- Generation evaluation benchmarks
- Embedding & vector sync operations

Provides:
- Task state machine (PENDING -> RUNNING -> COMPLETED / FAILED)
- In-memory async worker queue with concurrency throttle
- Structured status queries, execution error logs, and execution duration
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundTask:
    """Represents a scheduled or executed background job."""

    def __init__(
        self,
        task_id: str,
        name: str,
        coro_fn: Callable[..., Awaitable[Any]],
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        max_retries: int = 0,
    ) -> None:
        self.task_id = task_id
        self.name = name
        self.coro_fn = coro_fn
        self.args = args
        self.kwargs = kwargs or {}
        self.metadata = metadata or {}
        self.max_retries = max_retries
        self.retry_count = 0
        self.status = TaskStatus.PENDING
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        duration = None
        if self.started_at and self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            duration = (datetime.now(timezone.utc) - self.started_at).total_seconds()

        return {
            "task_id": self.task_id,
            "name": self.name,
            "status": self.status.value,
            "metadata": self.metadata,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
            "duration_seconds": duration,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AsyncTaskWorker:
    """
    In-process async task worker pool.
    Manages task queues and limits concurrent executions.
    """

    def __init__(self, concurrency: int = 2) -> None:
        self.concurrency = concurrency
        self._queue: asyncio.Queue[BackgroundTask] = asyncio.Queue()
        self._tasks: Dict[str, BackgroundTask] = {}
        self._workers: List[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        """Start worker loop tasks."""
        if self._running:
            return
        self._running = True
        for i in range(self.concurrency):
            worker_task = asyncio.create_task(self._worker_loop(worker_id=i))
            self._workers.append(worker_task)
        logger.info("AsyncTaskWorker started with %d workers", self.concurrency)

    async def stop(self) -> None:
        """Stop worker loops cleanly."""
        self._running = False
        for worker_task in self._workers:
            worker_task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("AsyncTaskWorker stopped.")

    def submit(
        self,
        name: str,
        coro_fn: Callable[..., Awaitable[Any]],
        *args: Any,
        metadata: Optional[Dict[str, Any]] = None,
        max_retries: int = 0,
        **kwargs: Any,
    ) -> str:
        """Submit a coroutine for background execution with optional retry limit."""
        task_id = str(uuid.uuid4())
        task = BackgroundTask(
            task_id=task_id,
            name=name,
            coro_fn=coro_fn,
            args=args,
            kwargs=kwargs,
            metadata=metadata,
            max_retries=max_retries,
        )
        self._tasks[task_id] = task
        self._queue.put_nowait(task)
        logger.info("Submitted task %s [%s] to queue (max_retries=%d)", task_id, name, max_retries)
        return task_id

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        sorted_tasks = sorted(
            self._tasks.values(), key=lambda t: t.created_at, reverse=True
        )
        return [t.to_dict() for t in sorted_tasks[:limit]]

    async def _worker_loop(self, worker_id: int) -> None:
        logger.debug("Worker-%d loop started", worker_id)
        while self._running:
            try:
                task = await self._queue.get()
            except asyncio.CancelledError:
                break

            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            logger.info("Worker-%d started task %s (%s)", worker_id, task.task_id, task.name)

            try:
                task.result = await task.coro_fn(*task.args, **task.kwargs)
                task.status = TaskStatus.COMPLETED
                logger.info("Worker-%d completed task %s (%s)", worker_id, task.task_id, task.name)
            except Exception as exc:
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.status = TaskStatus.PENDING
                    logger.warning(
                        "Worker-%d task %s (%s) failed (attempt %d/%d), re-queueing: %s",
                        worker_id, task.task_id, task.name, task.retry_count, task.max_retries, exc
                    )
                    self._queue.put_nowait(task)
                else:
                    task.status = TaskStatus.FAILED
                    task.error = str(exc)
                    logger.exception("Worker-%d failed task %s (%s): %s", worker_id, task.task_id, task.name, exc)
            finally:
                task.completed_at = datetime.now(timezone.utc)
                self._queue.task_done()


_global_worker: Optional[AsyncTaskWorker] = None


def get_task_worker() -> AsyncTaskWorker:
    """Return the global async task worker instance."""
    global _global_worker
    if _global_worker is None:
        _global_worker = AsyncTaskWorker(concurrency=2)
    return _global_worker
