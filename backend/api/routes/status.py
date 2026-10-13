"""
System status and dependency health endpoint.

Provides comprehensive live status of backend services and infrastructure.
"""
from __future__ import annotations

from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.config.settings import settings

router = APIRouter(tags=["status"])


class SystemStatusResponse(BaseModel):
    backend: str = "ok"
    database: str
    qdrant: str
    redis: str
    groq_configured: bool
    environment: str


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Detailed backend and dependencies status",
    description="Returns live connection state for PostgreSQL, Qdrant, Redis, and Groq configuration.",
)
async def get_system_status(
    db: AsyncSession = Depends(get_db),
) -> SystemStatusResponse:
    # 1. Database check
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # 2. Qdrant check
    qdrant_status = "ok"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{settings.QDRANT_URL.rstrip('/')}/healthz")
            if res.status_code != 200:
                qdrant_status = "degraded"
    except Exception:
        qdrant_status = "error"

    # 3. Redis check
    redis_status = "not_configured"
    if settings.REDIS_URL:
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
            await r.ping()
            await r.aclose()
            redis_status = "ok"
        except Exception:
            redis_status = "error"

    return SystemStatusResponse(
        backend="ok",
        database=db_status,
        qdrant=qdrant_status,
        redis=redis_status,
        groq_configured=bool(settings.GROQ_API_KEY),
        environment=settings.ENVIRONMENT.value,
    )

