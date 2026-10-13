"""
Tests for GET /health endpoint.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """Health endpoint must always return 200."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_has_required_fields(client: AsyncClient) -> None:
    """Response must include status, version, environment, uptime, and components."""
    response = await client.get("/health")
    data = response.json()

    assert "status" in data
    assert "version" in data
    assert "environment" in data
    assert "uptime_seconds" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_health_database_component_ok(client: AsyncClient) -> None:
    """Database component must report 'ok' when the test SQLite DB is reachable."""
    response = await client.get("/health")
    data = response.json()

    assert data["components"]["database"]["status"] == "ok"
    assert data["components"]["database"]["error"] is None


@pytest.mark.asyncio
async def test_health_overall_status_ok(client: AsyncClient) -> None:
    """Overall status must be 'ok' when all components are healthy."""
    response = await client.get("/health")
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_version_format(client: AsyncClient) -> None:
    """Version must be a non-empty string."""
    response = await client.get("/health")
    data = response.json()
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


@pytest.mark.asyncio
async def test_health_environment_is_testing(client: AsyncClient) -> None:
    """Environment must reflect the ENVIRONMENT=testing override set in conftest."""
    response = await client.get("/health")
    data = response.json()
    assert data["environment"] == "testing"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """Root endpoint returns application metadata."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "health" in data
