"""
Pydantic schemas for the Agentic RAG endpoint.

Request / Response contracts for POST /api/v1/repositories/{id}/agent/query.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Request ──────────────────────────────────────────────────────────────────


class AgentQueryRequest(BaseModel):
    """Request body for the agentic Q&A endpoint."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Developer question to answer using repository intelligence.",
        examples=["How does authentication work?", "Why was the login module refactored?"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of chunks to retrieve per tool call.",
    )
    max_reflections: int = Field(
        default=2,
        ge=0,
        le=3,
        description="Maximum self-correction cycles before forcing an answer.",
    )
    include_citations: bool = Field(
        default=True,
        description="Whether to include structured citation objects in the response.",
    )


# ─── Response ─────────────────────────────────────────────────────────────────


class AgentToolCallLog(BaseModel):
    """Record of one tool invocation inside the agent trace."""
    tool_name: str
    query: str
    result_count: int


class AgentQueryResponse(BaseModel):
    """Response from the agentic Q&A endpoint."""

    query: str
    repository_id: str
    intent: str = Field(description="Detected query intent: code | docs | git | general")
    answer: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    tool_calls: List[AgentToolCallLog] = Field(default_factory=list)
    reflection_count: int = Field(description="Number of self-correction cycles performed")
    tokens_used: Optional[int] = None
    model: str
