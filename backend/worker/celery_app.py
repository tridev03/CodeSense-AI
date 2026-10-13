"""
REL-01 Part 2: Distributed Celery Application Configuration.

Celery is the distributed task queue that replaces the in-process
AsyncTaskWorker when REDIS_URL is set in the environment.

Architecture:
  API Container  → celery.send_task("worker.tasks.index_repository", ...)
       ↓  (enqueues to Redis)
  Redis Broker   → stores job messages durably
       ↓  (workers poll and dequeue)
  Worker Container(s) → execute tasks, store results in Redis backend

Task Results:
  Results are stored in Redis with the same REDIS_URL.
  They are queryable via Celery's AsyncResult API, which the
  TaskStatusAdapter wraps for unified interface compatibility.

Configuration:
  All settings come from backend.config.settings (REDIS_URL, CELERY_CONCURRENCY,
  CELERY_TASK_SOFT_TIMEOUT_S, CELERY_TASK_HARD_TIMEOUT_S).

Import guard:
  This module is only imported when celery is installed AND REDIS_URL is configured.
  All callers must use the TaskQueueAdapter abstraction instead.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def make_celery_app():
    """
    Build and return a configured Celery application instance.

    Raises ImportError if celery is not installed.
    Raises ValueError if REDIS_URL is not configured.
    """
    try:
        from celery import Celery
    except ImportError as exc:
        raise ImportError(
            "Celery is not installed. Install it with: "
            "pip install 'celery[redis]>=5.4.0'"
        ) from exc

    from backend.config.settings import settings

    if not settings.REDIS_URL:
        raise ValueError(
            "REDIS_URL must be set in the environment to use the Celery task queue. "
            "Example: REDIS_URL=redis://localhost:6379/0"
        )

    redis_url = settings.REDIS_URL

    app = Celery(
        "ai_knowledge_agent",
        broker=redis_url,
        backend=redis_url,
    )

    app.conf.update(
        # ── Serialization ──────────────────────────────────────────────────
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # ── Reliability ────────────────────────────────────────────────────
        task_acks_late=True,            # Only ack after successful execution
        task_reject_on_worker_lost=True,  # Re-queue if worker dies mid-task
        worker_prefetch_multiplier=1,   # Prevent one worker from grabbing all jobs

        # ── Timeouts ───────────────────────────────────────────────────────
        task_soft_time_limit=settings.CELERY_TASK_SOFT_TIMEOUT_S,
        task_time_limit=settings.CELERY_TASK_HARD_TIMEOUT_S,

        # ── Results ────────────────────────────────────────────────────────
        result_expires=86400,           # Expire task results after 24 hours
        task_track_started=True,

        # ── Timezone ───────────────────────────────────────────────────────
        timezone="UTC",
        enable_utc=True,

        # ── Beat schedule (periodic tasks, if needed) ──────────────────────
        beat_schedule={},
    )

    # Auto-discover tasks in the worker package
    app.autodiscover_tasks(["backend.worker"])

    # Ensure tasks are registered immediately
    try:
        from backend.worker.celery_tasks import get_registered_tasks
        get_registered_tasks()
    except Exception as exc:
        logger.warning("Could not pre-register Celery tasks: %s", exc)

    logger.info("Celery app configured with broker=%s", redis_url[:30] + "…")
    return app


# Lazy singleton — only instantiated when REDIS_URL is available
_celery_app = None


def get_celery_app():
    """Return the Celery app instance, creating it on first call."""
    global _celery_app
    if _celery_app is None:
        _celery_app = make_celery_app()
    return _celery_app

app = get_celery_app()

# Register tasks on module import
try:
    from backend.worker.celery_tasks import get_registered_tasks
    get_registered_tasks()
except Exception:
    pass