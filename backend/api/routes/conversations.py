"""
Conversation and message persistence endpoints (CHAT-01).

Enables server-synced chat sessions, cross-device conversation history,
and message grounding retrieval.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.database import crud
from backend.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)
from backend.security.dependencies import CurrentUser, get_current_user

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get(
    "",
    response_model=List[ConversationResponse],
    summary="List conversations",
    description="Returns all conversation sessions for the authenticated user.",
)
async def list_conversations(
    repository_id: Optional[uuid.UUID] = Query(None, description="Filter by repository"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[ConversationResponse]:
    user_uuid = uuid.UUID(current_user.user_id) if current_user.user_id else None
    convs = await crud.list_conversations(
        db,
        user_id=user_uuid,
        repository_id=repository_id,
        skip=skip,
        limit=limit,
    )
    result = []
    for c in convs:
        # Load count of messages
        msgs = await crud.list_messages(db, c.id)
        result.append(
            ConversationResponse(
                id=c.id,
                title=c.title,
                user_id=c.user_id,
                repository_id=c.repository_id,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=len(msgs),
            )
        )
    return result


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a conversation",
)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationResponse:
    user_uuid = uuid.UUID(current_user.user_id) if current_user.user_id else None
    title = payload.title.strip() if payload.title and payload.title.strip() else "New Conversation"

    # Optional: verify repository exists if given
    if payload.repository_id is not None:
        repo = await crud.get_repository(db, payload.repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository {payload.repository_id} not found",
            )

    conv = await crud.create_conversation(
        db,
        user_id=user_uuid,
        repository_id=payload.repository_id,
        title=title,
    )
    await db.commit()
    await db.refresh(conv)

    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        user_id=conv.user_id,
        repository_id=conv.repository_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation details and full message history",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationDetailResponse:
    user_uuid = uuid.UUID(current_user.user_id) if current_user.user_id else None
    conv = await crud.get_conversation(db, conversation_id, user_id=user_uuid)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    msgs = await crud.list_messages(db, conversation_id)
    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        user_id=conv.user_id,
        repository_id=conv.repository_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[MessageResponse.model_validate(m) for m in msgs],
    )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update conversation title",
)
async def update_conversation_title(
    conversation_id: uuid.UUID,
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationResponse:
    user_uuid = uuid.UUID(current_user.user_id) if current_user.user_id else None
    title = (payload.title or "New Conversation").strip()
    conv = await crud.update_conversation_title(
        db, conversation_id, title=title, user_id=user_uuid
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )
    await db.commit()
    await db.refresh(conv)
    msgs = await crud.list_messages(db, conv.id)
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        user_id=conv.user_id,
        repository_id=conv.repository_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=len(msgs),
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and all its messages",
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user_uuid = uuid.UUID(current_user.user_id) if current_user.user_id else None
    deleted = await crud.delete_conversation(db, conversation_id, user_id=user_uuid)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )
    await db.commit()
    return None


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a message to a conversation",
)
async def append_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> MessageResponse:
    user_uuid = uuid.UUID(current_user.user_id) if current_user.user_id else None
    conv = await crud.get_conversation(db, conversation_id, user_id=user_uuid)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    msg = await crud.create_message(
        db,
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
        citations=payload.citations,
        model_name=payload.model_name,
        tokens_used=payload.tokens_used,
    )
    await db.commit()
    await db.refresh(msg)
    return MessageResponse.model_validate(msg)

