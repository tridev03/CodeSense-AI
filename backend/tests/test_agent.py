"""
Tests for Phase 6: Agentic RAG

Coverage:
  1. test_query_router_intent_detection     — intent classification for code/docs/git/general queries
  2. test_query_router_retry_mode           — retry mode forces all three tools
  3. test_execute_tools_deduplication       — duplicate chunks from multiple tools not duplicated
  4. test_reflector_proceeds_with_good_context   — adequate chunks → no retry
  5. test_reflector_retries_with_sparse_context  — too few chunks → retry flagged
  6. test_mock_agent_end_to_end             — full MockAgent pipeline via /agent/query endpoint
  7. test_agent_404_nonexistent_repository  — 404 for unknown repo
  8. test_agent_code_intent_routing         — code query uses search_code tool
  9. test_agent_git_intent_routing          — git query uses search_git_history tool
"""
from __future__ import annotations

import pytest
import uuid

from httpx import AsyncClient

from backend.agents.state import make_initial_state, AgentState
from backend.agents.nodes import route_query, reflect_on_context


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_chunk(file_path: str, start_line: int, content: str = "def foo(): pass") -> dict:
    """Helper: build a minimal code chunk dict."""
    return {
        "id": str(uuid.uuid4()),
        "content": content,
        "score": 0.9,
        "metadata": {
            "file_path": file_path,
            "start_line": start_line,
            "end_line": start_line + 5,
            "content_type": "code",
            "language": "python",
        },
    }


# ─── Unit Tests: Query Router ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query, expected_intent",
    [
        ("What class handles authentication?", "code"),
        ("How do I set up the project from README?", "docs"),
        ("Why was the login module refactored in the last commit?", "git"),
        ("Who changed the authentication flow?", "git"),
        ("What does this repository do?", "general"),
        ("Explain the architecture overview", "docs"),
        ("Show me the UserService class implementation", "code"),
    ],
)
def test_query_router_intent_detection(query: str, expected_intent: str):
    """Router correctly classifies query intent."""
    state = make_initial_state(query=query, repository_id="repo-1")
    result = route_query(state)
    assert result["intent"] == expected_intent, (
        f"Query {query!r} → expected intent={expected_intent!r} but got {result['intent']!r}"
    )


def test_query_router_retry_mode():
    """In retry mode, router always selects all three tools regardless of intent."""
    state = make_initial_state(query="How does auth work?", repository_id="repo-1")
    state["needs_retry"] = True
    state["retry_query"] = "explain authentication implementation"

    result = route_query(state)

    assert result["intent"] == "general"
    assert set(result["tools_to_run"]) == {"search_code", "search_docs", "search_git_history"}
    assert result.get("needs_retry") is False  # Cleared after routing


def test_query_router_code_intent_selects_search_code():
    """Code intent query selects search_code as the primary tool."""
    state = make_initial_state(query="Show me the UserService class", repository_id="repo-1")
    result = route_query(state)
    assert result["intent"] == "code"
    assert "search_code" in result["tools_to_run"]


def test_query_router_git_intent_selects_git_tool():
    """Git intent query selects search_git_history as the first tool."""
    state = make_initial_state(query="Who changed the auth module?", repository_id="repo-1")
    result = route_query(state)
    assert result["intent"] == "git"
    assert "search_git_history" in result["tools_to_run"]


# ─── Unit Tests: Reflector ────────────────────────────────────────────────────


def test_reflector_proceeds_with_adequate_context():
    """With sufficient relevant chunks, reflector proceeds to generation (no retry)."""
    state = make_initial_state(query="how does authentication work", repository_id="repo-1")
    state["context_chunks"] = [
        _make_chunk("auth/service.py", 10, "def authenticate_user(username, password): pass"),
        _make_chunk("auth/models.py", 20, "class UserAuthentication: pass"),
        _make_chunk("auth/utils.py", 30, "def hash_password(raw): return bcrypt.hash(raw)"),
    ]
    state["reflection_count"] = 0

    result = reflect_on_context(state)

    assert result.get("needs_retry") is False


def test_reflector_retries_on_empty_context():
    """With no chunks, reflector requests a retry and reformulates the query."""
    state = make_initial_state(query="how does login work", repository_id="repo-1")
    state["context_chunks"] = []
    state["reflection_count"] = 0

    result = reflect_on_context(state)

    assert result.get("needs_retry") is True
    assert result.get("retry_query") is not None
    assert result.get("reflection_count") == 1


def test_reflector_stops_retrying_at_max_reflections():
    """After MAX_REFLECTIONS cycles, reflector proceeds regardless of context quality."""
    state = make_initial_state(query="obscure query with no results", repository_id="repo-1")
    state["context_chunks"] = []
    state["reflection_count"] = 2   # Already at max

    result = reflect_on_context(state)

    assert result.get("needs_retry") is False


# ─── Integration Tests: Agent Endpoint ───────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_404_nonexistent_repository(client: AsyncClient):
    """Agent endpoint returns 404 for an unknown repository UUID."""
    fake_id = str(uuid.uuid4())
    response = await client.post(
        f"/api/v1/repositories/{fake_id}/agent/query",
        json={"query": "How does authentication work?"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mock_agent_end_to_end(client: AsyncClient):
    """
    Full end-to-end test through the agent endpoint using MockAgent.

    Steps:
      1. Create a repository.
      2. POST to /agent/query.
      3. Assert response structure matches AgentQueryResponse schema.
    """
    # 1. Create repository
    create_resp = await client.post(
        "/api/v1/repositories",
        json={"url": "https://github.com/agent-test/sample-repo"},
    )
    assert create_resp.status_code == 201
    repo_id = create_resp.json()["id"]

    # 2. Send agent query
    response = await client.post(
        f"/api/v1/repositories/{repo_id}/agent/query",
        json={
            "query": "How does authentication work in this codebase?",
            "top_k": 3,
            "max_reflections": 1,
            "include_citations": True,
        },
    )
    assert response.status_code == 200

    data = response.json()

    # 3. Validate schema fields
    assert data["query"] == "How does authentication work in this codebase?"
    assert data["repository_id"] == repo_id
    assert "intent" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert "tool_calls" in data
    assert isinstance(data["tool_calls"], list)
    assert "reflection_count" in data
    assert isinstance(data["reflection_count"], int)
    assert "citations" in data
    assert "model" in data


@pytest.mark.asyncio
async def test_agent_query_returns_tool_audit_log(client: AsyncClient):
    """Agent response includes a non-empty tool_calls audit log."""
    create_resp = await client.post(
        "/api/v1/repositories",
        json={"url": "https://github.com/agent-test/audit-repo"},
    )
    assert create_resp.status_code == 201
    repo_id = create_resp.json()["id"]

    response = await client.post(
        f"/api/v1/repositories/{repo_id}/agent/query",
        json={"query": "What is the class structure of this project?"},
    )
    assert response.status_code == 200
    data = response.json()

    # At least one tool call should be recorded
    assert len(data["tool_calls"]) >= 1
    for tc in data["tool_calls"]:
        assert "tool_name" in tc
        assert "query" in tc
        assert "result_count" in tc
