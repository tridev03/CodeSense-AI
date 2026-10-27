"""
Pydantic schemas for Conversations and Messages.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageCreate(BaseModel):
    role: str = Field(default="user", description="'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")
    citations: Optional[List[Dict[str, Any]]] = None
    model_name: Optional[str] = None
    tokens_used: Optional[int] = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: Optional[List[Dict[str, Any]]] = None
    model_name: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime

    @field_validator("citations", mode="before")
    @classmethod
    def parse_citations(cls, v: Any) -> Optional[List[Dict[str, Any]]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default="New Conversation")
    repository_id: Optional[uuid.UUID] = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    user_id: Optional[uuid.UUID] = None
    repository_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    user_id: Optional[uuid.UUID] = None
    repository_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = Field(default_factory=list)

