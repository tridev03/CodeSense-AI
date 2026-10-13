"""
AI Software Engineering Knowledge Agent — Backend Entry Point

Application lifecycle:
1. On startup: create DB tables, log config summary.
2. On shutdown: dispose DB connection pool.

Routes are registered with versioned prefixes (/api/v1).
The global exception handler ensures no raw tracebacks leak to clients.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

# Force UTF-8 stream encoding on Windows to prevent UnicodeEncodeError in cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config.settings import settings

# ─── Structured Logging Setup ─────────────────────────────────────────────────
# Must be configured before any logger is used.

_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]

if settings.is_development:
    _processors.append(structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()))
else:
    _processors.append(structlog.processors.JSONRenderer())

structlog.configure(
    processors=_processors,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    level=settings.LOG_LEVEL.value,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = structlog.get_logger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage startup and shutdown events.

    Startup:
    - Create database tables (development convenience; Phase 8 uses Alembic).

    Shutdown:
    - Dispose the connection pool to release all DB connections cleanly.
    """
    from backend.database.connection import create_tables, dispose_engine

    logger.info(
        "Application starting",
        app=settings.APP_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT.value,
        log_level=settings.LOG_LEVEL.value,
    )

    # Skip DB setup when running under pytest (test fixtures handle their own DB)
    if not settings.is_testing:
        try:
            await create_tables()
        except Exception as exc:
            logger.warning(
                "Database initialization failed during startup. Operating in degraded mode until database is available.",
                error=str(exc),
            )

    # Start background async task worker
    from backend.worker.tasks import get_task_worker
    worker = get_task_worker()
    await worker.start()

    yield  # Application is running

    logger.info("Application shutting down")

    # Stop background task worker
    await worker.stop()

    # Flush observability traces
    from backend.observability.tracer import get_tracer
    get_tracer().flush()
    get_tracer().shutdown()

    if not settings.is_testing:
        await dispose_engine()


# ─── FastAPI Application ──────────────────────────────────────────────────────


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "AI-powered developer intelligence system. "
        "Understands software repositories and answers developer questions "
        "using source code, documentation, and Git history."
    ),
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)


# ─── Middleware ────────────────────────────────────────────────────────────────

from backend.middleware.metrics import MetricsMiddleware  # noqa: E402
from backend.middleware.rate_limit import RateLimitMiddleware  # noqa: E402
from backend.middleware.request_id import RequestIDMiddleware  # noqa: E402

app.add_middleware(MetricsMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Cache-Control", "X-Accel-Buffering"],
)



# ─── Global Exception Handler ──────────────────────────────────────────────────


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all exception handler.

    - Logs the full traceback server-side.
    - Returns a safe generic message to the client (no stack traces in responses).
    """
    logger.exception(
        "Unhandled exception",
        path=str(request.url.path),
        method=request.method,
        exc_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

from backend.api.routes import (  # noqa: E402
    agent,
    auth,
    chat,
    evaluation,
    git,
    health,
    metrics,
    repositories,
    search,
    status as status_route,
    tasks,
)

app.include_router(health.router)
app.include_router(metrics.router)                               # OBS-07: Prometheus /metrics
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)   # SEC-01
app.include_router(repositories.router, prefix=settings.API_V1_PREFIX)
app.include_router(search.router, prefix=settings.API_V1_PREFIX)
app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
app.include_router(chat.direct_router, prefix=settings.API_V1_PREFIX)  # direct file chat
app.include_router(git.router, prefix=settings.API_V1_PREFIX)
app.include_router(agent.router, prefix=settings.API_V1_PREFIX)
app.include_router(evaluation.router, prefix=settings.API_V1_PREFIX)
app.include_router(tasks.router, prefix=settings.API_V1_PREFIX)
app.include_router(status_route.router, prefix=settings.API_V1_PREFIX)



# ─── Root ─────────────────────────────────────────────────────────────────────


@app.get("/", tags=["root"], include_in_schema=False)
async def root() -> Dict[str, Any]:
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health",
        "api": settings.API_V1_PREFIX,
    }
