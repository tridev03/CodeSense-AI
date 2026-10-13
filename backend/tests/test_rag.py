"""
Integration tests for Search and Chat API endpoints and RAGService.

Tests:
- POST /api/v1/repositories/{id}/search (semantic search, filters, 404)
- POST /api/v1/repositories/{id}/chat (grounded Q&A, citations, 404)
- End-to-end flow: Ingest repository -> Search code -> Chat with citations
"""
from __future__ import annotations

from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.embeddings import get_embedding_service
from backend.ingestion.pipeline import run_ingestion
from backend.retrieval import VectorStoreService
from backend.services.repository_service import RepositoryService
from backend.schemas.repository import RepositoryCreate


@pytest.fixture
def indexed_repo_path(tmp_path: Path) -> Path:
    """Create a sample repo with code and documentation files."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        '''class AuthService:
    """Core authentication logic."""
    def verify_token(self, token: str) -> bool:
        """Verify JWT token signature."""
        return token == "valid-token"
''',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        '''# Auth Service Documentation
This service handles JWT token verification and user sessions.
''',
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.asyncio
async def test_search_nonexistent_repository_returns_404(client: AsyncClient) -> None:
    """Searching a non-existent repo returns 404."""
    resp = await client.post(
        "/api/v1/repositories/00000000-0000-0000-0000-000000000000/search",
        json={"query": "token verification"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_nonexistent_repository_returns_404(client: AsyncClient) -> None:
    """Chatting with a non-existent repo returns 404."""
    resp = await client.post(
        "/api/v1/repositories/00000000-0000-0000-0000-000000000000/chat",
        json={"query": "How is authentication handled?"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_and_chat_end_to_end(
    client: AsyncClient, test_db: AsyncSession, indexed_repo_path: Path
) -> None:
    """Register, index, search, and chat with a repository."""
    # 1. Register repo
    service = RepositoryService(test_db)
    repo = await service.create_repository(
        RepositoryCreate(url=str(indexed_repo_path), name="Auth Project")
    )
    job = await service.trigger_indexing(repo.id)

    # 2. Ingest & index into vector store
    await service.execute_indexing(repo.id, job.id)

    # 3. Test Search Endpoint
    search_resp = await client.post(
        f"/api/v1/repositories/{repo.id}/search",
        json={"query": "verify_token", "top_k": 5},
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["repository_id"] == str(repo.id)
    assert search_data["total_results"] > 0
    assert any("auth.py" in r["file_path"] for r in search_data["results"])

    # 4. Test Search with language filter
    py_search = await client.post(
        f"/api/v1/repositories/{repo.id}/search",
        json={"query": "authentication", "language": "python"},
    )
    assert py_search.status_code == 200
    assert all(r["language"] == "python" for r in py_search.json()["results"])

    # 5. Test Chat Endpoint
    chat_resp = await client.post(
        f"/api/v1/repositories/{repo.id}/chat",
        json={"query": "How does token verification work?", "include_citations": True},
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["repository_id"] == str(repo.id)
    assert len(chat_data["answer"]) > 0
    assert len(chat_data["citations"]) > 0
    assert any("auth.py" in c["file_path"] for c in chat_data["citations"])

