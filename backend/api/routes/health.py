"""
Health check and probe endpoints (DEP-06, REL-11).

Provides:
- `/health`: General summary of service health and uptime.
- `/health/liveness`: Kubernetes/Docker liveness probe. Fast 200 OK without dependency checks
  to prevent restart loops during transient third-party outages.
- `/health/readiness`: Kubernetes/Docker readiness probe. Checks core dependencies (PostgreSQL,
  Qdrant, Redis if configured) to determine if traffic should be routed to this instance.
- `/health/startup`: Startup probe to verify initialization completion.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, Response, status
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.config.settings import settings

router = APIRouter(tags=["health"])

# Module-level start time for uptime reporting
_start_time: float = time.time()


@router.get(
    "/health/liveness",
    summary="Liveness probe",
    description="Kubernetes/Docker liveness probe. Always returns HTTP 200 if the process is alive.",
    status_code=status.HTTP_200_OK,
)
async def liveness_probe() -> Dict[str, str]:
    """Fast check to verify the event loop is active and accepting requests."""
    return {"status": "alive"}


@router.get(
    "/health/startup",
    summary="Startup probe",
    description="Kubernetes startup probe to verify container is initialized.",
    status_code=status.HTTP_200_OK,
)
async def startup_probe() -> Dict[str, Any]:
    """Verify application startup completion."""
    return {
        "status": "ready",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
    }


@router.get(
    "/health/readiness",
    summary="Readiness probe",
    description=(
        "Checks critical dependencies (PostgreSQL, Qdrant, Redis). "
        "Returns HTTP 200 if all ready, or HTTP 503 if a critical dependency is unavailable."
    ),
)
async def readiness_probe(
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Comprehensive readiness probe checking downstream dependencies."""
    components: Dict[str, Dict[str, str]] = {}
    is_ready = True

    # 1. Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        components["database"] = {"status": "ok"}
    except Exception as exc:
        is_ready = False
        components["database"] = {"status": "error", "error": type(exc).__name__}

    # 2. Check Qdrant Vector DB
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            q_res = await client.get(f"{settings.QDRANT_URL.rstrip('/')}/healthz")
            if q_res.status_code == 200:
                components["qdrant"] = {"status": "ok"}
            else:
                components["qdrant"] = {"status": "degraded"}
    except Exception as exc:
        # If Qdrant is down, mark as error or degraded
        components["qdrant"] = {"status": "error", "error": type(exc).__name__}
        if not settings.is_testing:
            is_ready = False

    # 3. Check Redis (if configured)
    if settings.REDIS_URL:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
            await r.ping()
            await r.aclose()
            components["redis"] = {"status": "ok"}
        except Exception as exc:
            components["redis"] = {"status": "error", "error": type(exc).__name__}
            if not settings.is_testing:
                is_ready = False

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "not_ready",
        "components": components,
    }


@router.get(
    "/health",
    summary="General health check",
    description="Returns service status, environment, version, and dependency summary.",
)
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """General health check endpoint for monitoring dashboards and reverse proxies."""
    db_status = "ok"
    db_error: str | None = None

    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "error"
        db_error = type(exc).__name__

    overall_status = "ok" if db_status == "ok" else "degraded"

    return {
        "status": overall_status,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT.value,
        "uptime_seconds": round(time.time() - _start_time, 2),
        "components": {
            "database": {
                "status": db_status,
                "error": db_error,
            },
        },
    }
