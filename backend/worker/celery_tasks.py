"""
REL-01 Part 2: Registered Celery Tasks.

These are the actual task functions that Celery worker containers execute.
Each task is a thin wrapper around the existing service layer so that both:
  (a) local AsyncTaskWorker (in-process)
  (b) distributed Celery workers (multi-container)
call the exact same business logic.

Task naming convention: "backend.worker.celery_tasks.<name>"

Important:
  Tasks use bind=True so they can access self.retry() for automatic
  retry with exponential backoff on transient failures.

Usage from API:
  from backend.worker.queue_adapter import get_task_queue
  queue = get_task_queue()
  task_id = await queue.submit_indexing_job(repository_id, repository_url)
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _get_celery() -> Any:
    """Import Celery app lazily to avoid import errors when Celery is absent."""
    from backend.worker.celery_app import get_celery_app
    return get_celery_app()


def register_tasks():
    """
    Register all Celery tasks onto the app instance.

    Called once at module import time when Celery is available.
    Returns the task registry dict.
    """
    celery = _get_celery()

    @celery.task(
        bind=True,
        name="backend.worker.celery_tasks.index_repository",
        max_retries=3,
        default_retry_delay=60,       # seconds before first retry
        autoretry_for=(Exception,),
        retry_backoff=True,           # exponential backoff
        retry_backoff_max=600,        # cap at 10 minutes
        acks_late=True,
    )
    def index_repository(self, repository_id: str) -> Dict[str, Any]:
        """
        Celery task: clone + parse + embed + index a single repository.

        This is the distributed version of RepositoryService.execute_indexing().
        Running in a Celery worker means this can scale across multiple containers
        and is durable — Redis re-delivers if the worker dies mid-execution.
        """
        import asyncio
        from backend.database.connection import get_db_context
        from backend.services.repository_service import RepositoryService
        import uuid

        logger.info("Celery: starting index_repository task for repo=%s", repository_id)

        async def _run():
            async with get_db_context() as db:
                svc = RepositoryService(db)
                return await svc.execute_indexing(uuid.UUID(repository_id))

        try:
            result = asyncio.run(_run())
            logger.info("Celery: completed index_repository for repo=%s", repository_id)
            return {"status": "completed", "repository_id": repository_id, "result": str(result)}
        except Exception as exc:
            logger.exception("Celery: index_repository failed for repo=%s: %s", repository_id, exc)
            raise self.retry(exc=exc)

    return {
        "index_repository": index_repository,
    }


# Module-level task registry (populated lazily)
_tasks: Dict[str, Any] = {}


def get_registered_tasks() -> Dict[str, Any]:
    """Return registered Celery tasks, initialising on first call."""
    global _tasks
    if not _tasks:
        try:
            _tasks = register_tasks()
        except Exception as exc:
            logger.warning("Celery task registration skipped: %s", exc)
    return _tasks


# Register tasks on import
get_registered_tasks()
