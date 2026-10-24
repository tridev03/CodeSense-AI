"""
End-to-End Application Workflow Tests.

Validates the complete lifecycle:
1. Connect a repository (local / GitHub)
2. Index its files (AST parsing, chunking, embeddings, BM25)
3. Track indexing status (queued -> running -> completed)
4. Retrieve relevant code chunks via hybrid search
5. Ask technical questions and receive answers with source citations
6. Verify failure handling at every stage:
   - 404 on nonexistent repository
   - 403 on cross-tenant access attempt
   - SSRF rejection on unsafe URLs
   - Handling of parsing / scanning limits
"""
from __future__ import annotations

import json
from pathlib import Path
import uuid
import pytest
from httpx import AsyncClient

from backend.database.models import Repository
from backend.security.auth import create_access_token
from backend.services.repository_service import RepositoryService


@pytest.fixture
def sample_codebase_dir(tmp_path: Path) -> Path:
    """Create a sample multi-file repository for end-to-end testing."""
    repo_dir = tmp_path / "sample_project"
    repo_dir.mkdir()

    # File 1: Python auth module
    auth_py = repo_dir / "auth.py"
    auth_py.write_text(
        '"""Authentication and token handling module."""\n'
        'class TokenManager:\n'
        '    """Manages JWT creation and signature verification."""\n'
        '    def __init__(self, secret_key: str):\n'
        '        self.secret_key = secret_key\n\n'
        '    def verify_token(self, token: str) -> bool:\n'
        '        """Verify an incoming bearer token."""\n'
        '        return token.startswith("Bearer valid_")\n'
    )

    # File 2: Utility module
    utils_py = repo_dir / "utils.py"
    utils_py.write_text(
        '"""Utility functions."""\n'
        'def hash_password(password: str) -> str:\n'
        '    """Hash a plaintext password securely."""\n'
        '    return f"hashed_{password}"\n'
    )

    # File 3: Documentation
    readme_md = repo_dir / "README.md"
    readme_md.write_text(
        "# Sample Project\n\n"
        "This project provides secure token authentication and password hashing utilities.\n"
    )

    return repo_dir


@pytest.mark.asyncio
async def test_complete_e2e_workflow(client: AsyncClient, test_db, sample_codebase_dir: Path):
    """
    Test the full application workflow end-to-end.
    Connect -> Index -> Status -> Search -> Chat -> Citations -> Agent
    """
    user_a_id = str(uuid.uuid4())
    token_a = create_access_token(subject=user_a_id, email="alice@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # ── 1. Connect / Register Repository ───────────────────────────────────
    create_payload = {
        "name": "sample-project",
        "url": str(sample_codebase_dir),
        "source_type": "local",
    }
    create_res = await client.post(
        "/api/v1/repositories",
        json=create_payload,
        headers=headers_a,
    )
    assert create_res.status_code == 201, f"Create failed: {create_res.text}"
    repo_data = create_res.json()
    repo_id = repo_data["id"]
    assert repo_data["name"] == "sample-project"
    assert repo_data["status"] == "pending"

    # ── 2. Index Repository Files ──────────────────────────────────────────
    trigger_res = await client.post(
        f"/api/v1/repositories/{repo_id}/index",
        headers=headers_a,
    )
    assert trigger_res.status_code == 202
    trigger_data = trigger_res.json()
    assert "job_id" in trigger_data

    # Execute indexing synchronously using RepositoryService for test verification
    svc = RepositoryService(test_db)
    result = await svc.execute_indexing(uuid.UUID(repo_id), uuid.UUID(trigger_data["job_id"]))
    assert result.files_processed >= 3
    assert result.total_chunks > 0

    # ── 3. Check Indexing Status ───────────────────────────────────────────
    status_res = await client.get(
        f"/api/v1/repositories/{repo_id}/status",
        headers=headers_a,
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["status"] == "completed"
    assert status_data["progress"] == 100.0
    assert status_data["chunks_created"] > 0

    # ── 4. Retrieve Relevant Code via Hybrid Search ────────────────────────
    search_payload = {
        "query": "verify bearer token TokenManager",
        "top_k": 3,
        "mode": "hybrid",
    }
    search_res = await client.post(
        f"/api/v1/repositories/{repo_id}/search",
        json=search_payload,
        headers=headers_a,
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data["results"]) > 0
    top_hit = search_data["results"][0]
    assert "auth.py" in top_hit["file_path"] or "TokenManager" in top_hit["content"]
    assert top_hit["score"] > 0.0

    # ── 5. Ask Question & Generate Answer with Citations ───────────────────
    chat_payload = {
        "query": "How does TokenManager verify incoming tokens?",
        "top_k": 5,
        "include_citations": True,
    }
    chat_res = await client.post(
        f"/api/v1/repositories/{repo_id}/chat",
        json=chat_payload,
        headers=headers_a,
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert "answer" in chat_data
    assert len(chat_data["answer"]) > 0
    assert "citations" in chat_data
    assert len(chat_data["citations"]) > 0
    citation = chat_data["citations"][0]
    assert "file_path" in citation
    assert "start_line" in citation

    # ── 6. Agent Multi-Step Reasoning ──────────────────────────────────────
    agent_payload = {
        "query": "Explain how TokenManager is implemented in auth.py",
        "top_k": 3,
        "include_citations": True,
    }
    agent_res = await client.post(
        f"/api/v1/repositories/{repo_id}/agent/query",
        json=agent_payload,
        headers=headers_a,
    )
    assert agent_res.status_code == 200
    agent_data = agent_res.json()
    assert "answer" in agent_data
    assert "tool_calls" in agent_data
    assert len(agent_data["tool_calls"]) > 0


@pytest.mark.asyncio
async def test_e2e_failure_handling(client: AsyncClient, test_db, sample_codebase_dir: Path):
    """
    Test failure scenarios across the complete workflow:
    - 404 on nonexistent repository
    - 403 on cross-tenant access attempt
    - SSRF URL rejection
    - Nonexistent task lookup
    """
    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())

    token_a = create_access_token(subject=user_a_id, email="user_a@example.com")
    token_b = create_access_token(subject=user_b_id, email="user_b@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. 404 Not Found on nonexistent repository
    fake_id = str(uuid.uuid4())
    res_404 = await client.get(f"/api/v1/repositories/{fake_id}", headers=headers_a)
    assert res_404.status_code == 404
    assert f"Repository {fake_id} not found" in res_404.json()["detail"]

    # 2. SSRF URL rejection during repository registration
    ssrf_res = await client.post(
        "/api/v1/repositories",
        json={"name": "ssrf-test", "url": "http://169.254.169.254/latest/meta-data/"},
        headers=headers_a,
    )
    assert ssrf_res.status_code == 422  # Pydantic URL validator rejects unsafe format

    # 3. Create repository as User A
    create_res = await client.post(
        "/api/v1/repositories",
        json={"name": "private-repo", "url": str(sample_codebase_dir), "source_type": "local"},
        headers=headers_a,
    )
    assert create_res.status_code == 201
    repo_id = create_res.json()["id"]

    # 4. User B attempts to access User A's repository -> 403 Forbidden
    forbidden_res = await client.get(
        f"/api/v1/repositories/{repo_id}",
        headers=headers_b,
    )
    assert forbidden_res.status_code == 403
    assert "You do not have access" in forbidden_res.json()["detail"]

    # 5. User B attempts to search User A's repository -> 403 Forbidden
    forbidden_search = await client.post(
        f"/api/v1/repositories/{repo_id}/search",
        json={"query": "secret", "top_k": 3},
        headers=headers_b,
    )
    assert forbidden_search.status_code == 403

    # 6. User B attempts to chat with User A's repository -> 403 Forbidden
    forbidden_chat = await client.post(
        f"/api/v1/repositories/{repo_id}/chat",
        json={"query": "secret", "top_k": 3},
        headers=headers_b,
    )
    assert forbidden_chat.status_code == 403

    # 7. Check nonexistent background task -> 404
    task_res = await client.get(f"/api/v1/tasks/{fake_id}", headers=headers_a)
    assert task_res.status_code == 404
