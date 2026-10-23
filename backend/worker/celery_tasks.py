"""
Celery task definitions for the AI Knowledge Agent worker.

Tasks are defined at module level using the Celery app instance.
The app is imported lazily inside the task body to avoid circular imports.

Task naming convention: "backend.worker.celery_tasks.<name>"
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ── Import Celery app (celery_app does NOT import this module anymore) ──────
from backend.worker.celery_app import get_celery_app

celery = get_celery_app()


@celery.task(
    bind=True,
    name="backend.worker.celery_tasks.index_repository",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True,
)
def index_repository(self, repository_id: str) -> Dict[str, Any]:
    """
    Celery task: clone + parse + embed + index a single repository.

    This is the distributed version of RepositoryService.execute_indexing().
    """
    import asyncio
    import uuid
    from backend.database.connection import get_db_context
    from backend.services.repository_service import RepositoryService

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


def get_registered_tasks() -> Dict[str, Any]:
    """Return the task registry (kept for backward compatibility)."""
    return {"index_repository": index_repository}
