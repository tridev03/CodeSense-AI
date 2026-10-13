"""
Tests for Phase 8: Production Engineering & Observability.

Coverage:
  1. test_alembic_config_and_migrations
  2. test_request_id_middleware_header
  3. test_request_id_middleware_custom_header
  4. test_rate_limit_middleware_enforcement
  5. test_background_task_worker_lifecycle
  6. test_background_task_worker_failure_handling
  7. test_background_tasks_endpoints
  8. test_langfuse_tracer_noop_and_telemetry
"""
from __future__ import annotations

import asyncio
import uuid
import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient
from fastapi import FastAPI

import alembic.config
import alembic.script
from backend.database.models import Base
from backend.middleware.rate_limit import RateLimitMiddleware
from backend.middleware.request_id import RequestIDMiddleware
from backend.observability.tracer import LangfuseTracer, NoopTracer, get_tracer
from backend.worker.tasks import AsyncTaskWorker, TaskStatus


# ─── 1. Alembic Migrations Tests ─────────────────────────────────────────────


def test_alembic_config_and_migrations():
    """Verify Alembic configuration and initial migration discovery."""
    cfg = alembic.config.Config("alembic.ini")
    script = alembic.script.ScriptDirectory.from_config(cfg)
    revisions = list(script.walk_revisions())

    assert len(revisions) >= 1
    initial_rev = revisions[-1]
    assert initial_rev.revision == "001_initial_schema"

    # Verify SQLAlchemy metadata has both core tables
    table_names = set(Base.metadata.tables.keys())
    assert "repositories" in table_names
    assert "indexing_jobs" in table_names


# ─── 2. Request-ID Middleware Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_id_middleware_header(client: AsyncClient):
    """X-Request-ID header is generated and returned on all API responses."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 10


@pytest.mark.asyncio
async def test_request_id_middleware_custom_header(client: AsyncClient):
    """Client-provided X-Request-ID is preserved across request-response lifecycle."""
    custom_id = f"client-req-{uuid.uuid4()}"
    resp = await client.get("/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_id


# ─── 3. Rate Limit Middleware Tests ──────────────────────────────────────────


def test_rate_limit_middleware_enforcement():
    """RateLimitMiddleware blocks requests with 429 when max_requests is exceeded."""
    test_app = FastAPI()
    test_app.add_middleware(
        RateLimitMiddleware,
        max_requests=2,
        window_seconds=60,
        enabled=True,
    )

    @test_app.get("/test-endpoint")
    def sample():
        return {"ok": True}

    tc = TestClient(test_app)

    r1 = tc.get("/test-endpoint")
    assert r1.status_code == 200

    r2 = tc.get("/test-endpoint")
    assert r2.status_code == 200

    r3 = tc.get("/test-endpoint")
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers
    assert r3.json()["max_requests"] == 2


# ─── 4. Background Task Worker Tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_background_task_worker_lifecycle():
    """AsyncTaskWorker executes submitted tasks and transitions states to COMPLETED."""
    worker = AsyncTaskWorker(concurrency=1)
    await worker.start()

    executed = False

    async def mock_job(val: int):
        nonlocal executed
        await asyncio.sleep(0.01)
        executed = True
        return val * 2

    task_id = worker.submit("double_job", mock_job, 21)
    task = worker.get_task(task_id)
    assert task is not None
    assert task.status in (TaskStatus.PENDING, TaskStatus.RUNNING)

    # Wait for execution
    for _ in range(50):
        if task.status == TaskStatus.COMPLETED:
            break
        await asyncio.sleep(0.02)

    assert task.status == TaskStatus.COMPLETED
    assert task.result == 42
    assert executed is True
    assert task.to_dict()["duration_seconds"] is not None

    await worker.stop()


@pytest.mark.asyncio
async def test_background_task_worker_failure_handling():
    """AsyncTaskWorker catches task errors and marks them as FAILED without crashing."""
    worker = AsyncTaskWorker(concurrency=1)
    await worker.start()

    async def failing_job():
        raise RuntimeError("Intentional job failure")

    task_id = worker.submit("failing_job", failing_job)
    task = worker.get_task(task_id)

    for _ in range(50):
        if task.status == TaskStatus.FAILED:
            break
        await asyncio.sleep(0.02)

    assert task.status == TaskStatus.FAILED
    assert "Intentional job failure" in (task.error or "")

    await worker.stop()


# ─── 5. Tasks API Endpoints Tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_background_tasks_endpoints(client: AsyncClient):
    """GET /api/v1/tasks lists tasks and /api/v1/tasks/{id} returns details."""
    list_resp = await client.get("/api/v1/tasks")
    assert list_resp.status_code == 200
    assert isinstance(list_resp.json(), list)

    unknown_id = str(uuid.uuid4())
    not_found_resp = await client.get(f"/api/v1/tasks/{unknown_id}")
    assert not_found_resp.status_code == 404


# ─── 6. Observability & Langfuse Tracer Tests ─────────────────────────────────


def test_langfuse_tracer_noop_and_telemetry():
    """NoopTracer and LangfuseTracer handle spans and generation tracing safely."""
    tracer = get_tracer()
    assert tracer is not None

    # Test span context manager
    with tracer.span("test-span", metadata={"repo": "test"}) as s:
        s.update(tags=["unit-test"])

    # Test generation tracing context manager
    with tracer.trace_generation(
        name="test-gen",
        model="qwen/qwen3.8-27b",
        input_data="Hello",
        metadata={"temp": 0.1},
    ) as gen:
        gen.end()

    # Test retrieval tracing context manager
    with tracer.trace_retrieval(name="hybrid", query="search auth", top_k=5) as r:
        r.end()

    tracer.flush()
    tracer.shutdown()
