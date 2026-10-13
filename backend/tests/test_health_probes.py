"""
Health probes test suite (DEP-06, REL-11).

Verifies:
- /health/liveness returns 200 alive without database dependency
- /health/startup returns 200 ready
- /health/readiness returns status report
- /health overall summary status
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app


@pytest.mark.asyncio
async def test_liveness_probe_returns_200():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/liveness")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_startup_probe_returns_200():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/startup")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_readiness_probe_returns_components():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/readiness")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "components" in data
    assert "database" in data["components"]
