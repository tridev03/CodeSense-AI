"""
Tests for persistent conversations and message history (CHAT-01).
"""
import uuid
import pytest
from httpx import AsyncClient

from backend.security.dependencies import CurrentUser, get_current_user
from backend.main import app


@pytest.fixture
def auth_user_a():
    return CurrentUser(
        user_id="11111111-1111-1111-1111-111111111111",
        email="user_a@test.com",
        is_superuser=False,
    )


@pytest.fixture
def auth_user_b():
    return CurrentUser(
        user_id="22222222-2222-2222-2222-222222222222",
        email="user_b@test.com",
        is_superuser=False,
    )


@pytest.mark.asyncio
async def test_create_and_list_conversations(client: AsyncClient, auth_user_a):
    app.dependency_overrides[get_current_user] = lambda: auth_user_a

    # 1. Create a conversation
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Investigating Auth System"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    conv_id = data["id"]
    assert data["title"] == "Investigating Auth System"
    assert data["user_id"] == auth_user_a.user_id
    assert data["message_count"] == 0

    # 2. List conversations
    resp = await client.get("/api/v1/conversations")
    assert resp.status_code == 200
    convs = resp.json()
    assert len(convs) >= 1
    assert any(c["id"] == conv_id for c in convs)


@pytest.mark.asyncio
async def test_append_messages_and_get_details(client: AsyncClient, auth_user_a):
    app.dependency_overrides[get_current_user] = lambda: auth_user_a

    # 1. Create conversation
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Architecture Q&A"},
    )
    conv_id = resp.json()["id"]

    # 2. Append user message
    resp_msg1 = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={
            "role": "user",
            "content": "Where is the rate limiter defined?",
        },
    )
    assert resp_msg1.status_code == 201
    msg1 = resp_msg1.json()
    assert msg1["role"] == "user"
    assert msg1["content"] == "Where is the rate limiter defined?"

    # 3. Append assistant message with citations
    citations = [
        {
            "file_path": "backend/middleware/rate_limit.py",
            "start_line": 20,
            "end_line": 45,
            "snippet": "class RateLimitMiddleware: ...",
        }
    ]
    resp_msg2 = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={
            "role": "assistant",
            "content": "The rate limiter is defined in RateLimitMiddleware.",
            "citations": citations,
            "model_name": "claude-3-5-sonnet",
            "tokens_used": 150,
        },
    )
    assert resp_msg2.status_code == 201
    msg2 = resp_msg2.json()
    assert msg2["role"] == "assistant"
    assert len(msg2["citations"]) == 1
    assert msg2["citations"][0]["file_path"] == "backend/middleware/rate_limit.py"
    assert msg2["tokens_used"] == 150

    # 4. Fetch conversation detail
    resp_detail = await client.get(f"/api/v1/conversations/{conv_id}")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][1]["role"] == "assistant"
    assert detail["messages"][1]["citations"][0]["start_line"] == 20


@pytest.mark.asyncio
async def test_update_and_delete_conversation(client: AsyncClient, auth_user_a):
    app.dependency_overrides[get_current_user] = lambda: auth_user_a

    # 1. Create conversation
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Old Title"},
    )
    conv_id = resp.json()["id"]

    # 2. Update title
    resp_update = await client.patch(
        f"/api/v1/conversations/{conv_id}",
        json={"title": "Updated Modern Title"},
    )
    assert resp_update.status_code == 200
    assert resp_update.json()["title"] == "Updated Modern Title"

    # 3. Delete conversation
    resp_del = await client.delete(f"/api/v1/conversations/{conv_id}")
    assert resp_del.status_code == 204

    # 4. Confirm it is gone
    resp_get = await client.get(f"/api/v1/conversations/{conv_id}")
    assert resp_get.status_code == 404


@pytest.mark.asyncio
async def test_conversation_tenant_isolation(client: AsyncClient, auth_user_a, auth_user_b):
    # User A creates a conversation
    app.dependency_overrides[get_current_user] = lambda: auth_user_a
    resp_a = await client.post(
        "/api/v1/conversations",
        json={"title": "Secret Session of User A"},
    )
    conv_a_id = resp_a.json()["id"]

    # User B tries to view User A's conversation
    app.dependency_overrides[get_current_user] = lambda: auth_user_b
    resp_b_view = await client.get(f"/api/v1/conversations/{conv_a_id}")
    assert resp_b_view.status_code == 404

    # User B list conversations: should NOT see User A's conversation
    resp_b_list = await client.get("/api/v1/conversations")
    assert resp_b_list.status_code == 200
    b_conv_ids = [c["id"] for c in resp_b_list.json()]
    assert conv_a_id not in b_conv_ids

    # User B cannot delete User A's conversation
    resp_b_del = await client.delete(f"/api/v1/conversations/{conv_a_id}")
    assert resp_b_del.status_code == 404

