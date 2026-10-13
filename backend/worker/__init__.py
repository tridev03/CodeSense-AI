"""
backend.worker package.

Provides asynchronous background task queue, job worker pool, and task status tracking.

Mode A — Local (default): AsyncTaskWorker backed by asyncio.Queue.
Mode B — Distributed: Redis/Celery queue (activated when REDIS_URL is set).

Use get_task_queue() for the unified adapter that auto-selects the active mode.
"""
from backend.worker.tasks import (
    AsyncTaskWorker,
    BackgroundTask,
    TaskStatus,
    get_task_worker,
)
from backend.worker.queue_adapter import (
    BaseTaskQueue,
    LocalTaskQueue,
    RedisTaskQueue,
    TaskInfo,
    get_task_queue,
    reset_task_queue,
)

__all__ = [
    # In-process worker
    "AsyncTaskWorker",
    "BackgroundTask",
    "TaskStatus",
    "get_task_worker",
    # Unified adapter
    "BaseTaskQueue",
    "LocalTaskQueue",
    "RedisTaskQueue",
    "TaskInfo",
    "get_task_queue",
    "reset_task_queue",
]
