"""
Tests for the Repository API endpoints.

Coverage:
- POST /api/v1/repositories (create, duplicate, invalid URL)
- GET  /api/v1/repositories (list, pagination)
- GET  /api/v1/repositories/{id} (get, not found)
- DELETE /api/v1/repositories/{id} (delete, not found, cascade)
- POST /api/v1/repositories/{id}/index (trigger indexing)
- GET  /api/v1/repositories/{id}/status (indexing status)

Each test gets a fresh in-memory database via conftest.py fixtures.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

API = "/api/v1/repositories"


# ─── Fixtures / Helpers ───────────────────────────────────────────────────────


async def _create_repo(client: AsyncClient, url: str, **kwargs) -> dict:
    """Helper: create a repository and assert 201."""
    payload = {"url": url, **kwargs}
    r = await client.post(API, json=payload)
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    return r.json()


# ─── Create ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_github_repository(client: AsyncClient) -> None:
    """GitHub URL registers successfully with correct defaults."""
    repo = await _create_repo(client, "https://github.com/tiangolo/fastapi")

    assert repo["url"] == "https://github.com/tiangolo/fastapi"
    assert repo["source_type"] == "github"
    assert repo["status"] == "pending"
    assert repo["name"] == "tiangolo/fastapi"
    assert repo["branch"] == "main"
    assert "id" in repo
    assert "created_at" in repo
    assert "updated_at" in repo


@pytest.mark.asyncio
async def test_create_repository_custom_name_and_branch(client: AsyncClient) -> None:
    """Custom name and branch are preserved."""
    repo = await _create_repo(
        client,
        "https://github.com/pallets/flask",
        name="Flask Framework",
        branch="3.0.x",
        description="The Flask web framework",
    )
    assert repo["name"] == "Flask Framework"
    assert repo["branch"] == "3.0.x"
    assert repo["description"] == "The Flask web framework"


@pytest.mark.asyncio
async def test_create_repository_slug_name_extraction(client: AsyncClient) -> None:
    """Name is automatically extracted from the GitHub URL when not provided."""
    repo = await _create_repo(
        client, "https://github.com/encode/starlette.git"
    )
    assert repo["name"] == "encode/starlette"


@pytest.mark.asyncio
async def test_create_local_repository(client: AsyncClient) -> None:
    """Absolute local paths register as source_type=local."""
    repo = await _create_repo(client, "/home/user/my-project")
    assert repo["source_type"] == "local"
    assert repo["name"] == "my-project"


@pytest.mark.asyncio
async def test_create_duplicate_url_returns_409(client: AsyncClient) -> None:
    """Registering the same URL twice must return 409 Conflict."""
    url = "https://github.com/django/django"
    await _create_repo(client, url)
    r2 = await client.post(API, json={"url": url})
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_create_invalid_url_returns_422(client: AsyncClient) -> None:
    """Non-absolute, non-GitHub URLs must fail Pydantic validation (422)."""
    for bad_url in [
        "not-a-url",
        "ftp://example.com/repo",
        "relative/path",
        "",
    ]:
        r = await client.post(API, json={"url": bad_url})
        assert r.status_code == 422, f"Expected 422 for {bad_url!r}, got {r.status_code}"


@pytest.mark.asyncio
async def test_create_github_url_missing_repo_returns_422(client: AsyncClient) -> None:
    """GitHub URL without a repo slug (owner only) must fail validation."""
    r = await client.post(API, json={"url": "https://github.com/tiangolo"})
    assert r.status_code == 422


# ─── List ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_repositories_empty(client: AsyncClient) -> None:
    """List on empty database returns empty items and total=0."""
    r = await client.get(API)
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_repositories_returns_created(client: AsyncClient) -> None:
    """Created repositories appear in the listing."""
    await _create_repo(client, "https://github.com/sqlalchemy/sqlalchemy")
    await _create_repo(client, "https://github.com/pydantic/pydantic")

    r = await client.get(API)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_repositories_pagination(client: AsyncClient) -> None:
    """Pagination parameters (skip, limit) are respected."""
    for i in range(5):
        await _create_repo(client, f"https://github.com/owner/repo-{i}")

    r = await client.get(API, params={"skip": 2, "limit": 2})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["skip"] == 2
    assert data["limit"] == 2


@pytest.mark.asyncio
async def test_list_repositories_limit_validation(client: AsyncClient) -> None:
    """limit must be between 1 and 100."""
    r = await client.get(API, params={"limit": 0})
    assert r.status_code == 422

    r = await client.get(API, params={"limit": 101})
    assert r.status_code == 422


# ─── Get ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_repository_by_id(client: AsyncClient) -> None:
    """Fetching a repository by its UUID returns the correct record."""
    created = await _create_repo(client, "https://github.com/encode/httpx")
    repo_id = created["id"]

    r = await client.get(f"{API}/{repo_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == repo_id
    assert data["url"] == "https://github.com/encode/httpx"


@pytest.mark.asyncio
async def test_get_repository_not_found(client: AsyncClient) -> None:
    """Non-existent UUID returns 404."""
    r = await client.get(f"{API}/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_repository_invalid_uuid(client: AsyncClient) -> None:
    """Malformed UUID returns 422 (FastAPI path parameter validation)."""
    r = await client.get(f"{API}/not-a-uuid")
    assert r.status_code == 422


# ─── Delete ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_repository(client: AsyncClient) -> None:
    """Deleting a repository returns 204 and subsequent GET returns 404."""
    created = await _create_repo(client, "https://github.com/aio-libs/aiohttp")
    repo_id = created["id"]

    del_r = await client.delete(f"{API}/{repo_id}")
    assert del_r.status_code == 204

    get_r = await client.get(f"{API}/{repo_id}")
    assert get_r.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_repository(client: AsyncClient) -> None:
    """Deleting a non-existent repository returns 404."""
    r = await client.delete(f"{API}/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ─── Indexing ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_indexing_returns_202(client: AsyncClient) -> None:
    """Triggering indexing on an existing repository returns 202 with job info."""
    created = await _create_repo(client, "https://github.com/samuelcolvin/pydantic")
    repo_id = created["id"]

    r = await client.post(f"{API}/{repo_id}/index")
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert data["repository_id"] == repo_id
    assert "message" in data


@pytest.mark.asyncio
async def test_trigger_indexing_nonexistent_repo(client: AsyncClient) -> None:
    """Triggering indexing on a non-existent repository returns 404."""
    r = await client.post(f"{API}/00000000-0000-0000-0000-000000000000/index")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_indexing_status_after_trigger(client: AsyncClient) -> None:
    """After triggering, status endpoint returns a pending job."""
    created = await _create_repo(client, "https://github.com/tortoise/tortoise-orm")
    repo_id = created["id"]

    await client.post(f"{API}/{repo_id}/index")

    r = await client.get(f"{API}/{repo_id}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "pending"
    assert data["repository_id"] == repo_id
    assert data["progress"] == 0.0
    assert data["files_processed"] == 0
    assert data["chunks_created"] == 0


@pytest.mark.asyncio
async def test_get_indexing_status_before_trigger(client: AsyncClient) -> None:
    """Before any indexing is triggered, status returns null."""
    created = await _create_repo(client, "https://github.com/encode/uvicorn")
    repo_id = created["id"]

    r = await client.get(f"{API}/{repo_id}/status")
    assert r.status_code == 200
    # Returns null (no jobs yet)
    assert r.json() is None


@pytest.mark.asyncio
async def test_get_indexing_status_nonexistent_repo(client: AsyncClient) -> None:
    """Status check on non-existent repository returns 404."""
    r = await client.get(f"{API}/00000000-0000-0000-0000-000000000000/status")
    assert r.status_code == 404
