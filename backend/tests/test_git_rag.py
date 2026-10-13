"""
Integration tests for Git Intelligence endpoints and historical Q&A.

Tests:
- GET /api/v1/repositories/{id}/git/commits
- POST /api/v1/repositories/{id}/git/search
- POST /api/v1/repositories/{id}/git/file-history
- POST /api/v1/repositories/{id}/chat with Git history citations
"""
from __future__ import annotations

from pathlib import Path
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.git_extractor import create_mock_git_history
from backend.ingestion.models import GitCommitInfo
from backend.schemas.repository import RepositoryCreate
from backend.services.repository_service import RepositoryService


@pytest.fixture
def git_repo_with_history(tmp_path: Path) -> Path:
    """Create a repository folder with simulated Git history for testing."""
    commits = [
        GitCommitInfo(
            hash="c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1",
            short_hash="c2d3e4f5",
            author_name="Developer Dave",
            author_email="dave@example.com",
            date="2026-04-05T14:20:00Z",
            message="Feature: implement token verification in AuthManager",
            changed_files=["auth.py"],
            diff_summary="--- auth.py\n+++ auth.py\n@@ -1,2 +1,3 @@\n class AuthManager:\n+    def verify_token(self): return True\n",
        ),
        GitCommitInfo(
            hash="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            short_hash="a1b2c3d4",
            author_name="Developer Dave",
            author_email="dave@example.com",
            date="2026-04-01T09:00:00Z",
            message="Initial setup of AuthManager",
            changed_files=["auth.py"],
            diff_summary="--- /dev/null\n+++ auth.py\n@@ -0,0 +1,2 @@\n+class AuthManager:\n+    pass\n",
        ),
    ]
    create_mock_git_history(str(tmp_path), commits)

    auth_file = tmp_path / "auth.py"
    auth_file.write_text(
        "class AuthManager:\n    def verify_token(self): return True\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.asyncio
async def test_git_intelligence_pipeline_and_endpoints(
    client: AsyncClient, test_db: AsyncSession, git_repo_with_history: Path
) -> None:
    """Verify Git commit indexing, search, file history, and chat citations."""
    service = RepositoryService(test_db)
    repo = await service.create_repository(
        RepositoryCreate(url=str(git_repo_with_history), name="Git Intelligence Repo")
    )
    job = await service.trigger_indexing(repo.id)
    await service.execute_indexing(repo.id, job.id)

    # 1. Test GET /git/commits
    commits_resp = await client.get(f"/api/v1/repositories/{repo.id}/git/commits")
    assert commits_resp.status_code == 200
    data = commits_resp.json()
    assert data["total_commits"] == 2
    assert len(data["commits"]) == 2
    assert "token verification" in data["commits"][0]["message"]
    assert data["commits"][0]["author_name"] == "Developer Dave"

    # 2. Test POST /git/search
    search_resp = await client.post(
        f"/api/v1/repositories/{repo.id}/git/search",
        json={"query": "token verification", "top_k": 5},
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total_results"] > 0
    assert any("AuthManager" in r["content"] for r in search_data["results"])

    # 3. Test POST /git/file-history
    file_hist_resp = await client.post(
        f"/api/v1/repositories/{repo.id}/git/file-history",
        json={"file_path": "auth.py"},
    )
    assert file_hist_resp.status_code == 200
    file_hist_data = file_hist_resp.json()
    assert file_hist_data["total_commits"] == 2
    assert file_hist_data["file_path"] == "auth.py"

    # 4. Test POST /chat with Git historical question
    chat_resp = await client.post(
        f"/api/v1/repositories/{repo.id}/chat",
        json={
            "query": "Why was token verification added?",
            "include_citations": True,
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert len(chat_data["answer"]) > 0
    assert len(chat_data["citations"]) > 0
    assert any("commit:" in (c.get("symbol") or "") for c in chat_data["citations"])
