"""
Chat and question-answering endpoints.

Allows asking technical questions about a repository with context-grounded
evidence citations.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.schemas.rag import ChatRequest, ChatResponse, ChatStreamChunk
from backend.services.rag_service import RAGService
from backend.services.repository_service import RepositoryNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repositories", tags=["chat"])


def _rag_service(db: AsyncSession = Depends(get_db)) -> RAGService:
    return RAGService(db)


@router.post(
    "/{repository_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question about a repository",
    description="Retrieves relevant codebase evidence and generates a grounded response with source citations.",
)
async def chat_repository(
    repository_id: uuid.UUID,
    payload: ChatRequest,
    rag_svc: RAGService = Depends(_rag_service),
) -> ChatResponse:
    try:
        return await rag_svc.chat(repository_id, payload)
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{repository_id}/chat/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream a chat response using Server-Sent Events",
    description=(
        "Retrieves relevant codebase evidence and streams the LLM answer token-by-token "
        "as SSE events. The final event includes citations and `done: true`."
    ),
)
async def chat_repository_stream(
    repository_id: uuid.UUID,
    payload: ChatRequest,
    rag_svc: RAGService = Depends(_rag_service),
) -> StreamingResponse:
    """
    SSE streaming endpoint for chat.

    Event format:
        data: {"token": "Hello"}\\n\\n
        data: {"token": " world"}\\n\\n
        data: {"citations": [...], "done": true}\\n\\n
    On error:
        data: {"error": "message", "done": true}\\n\\n
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for kind, payload_data in rag_svc.chat_stream(repository_id, payload):
                if kind == "token":
                    chunk = ChatStreamChunk(token=payload_data)
                else:  # "done"
                    chunk = ChatStreamChunk(done=True, citations=payload_data)
                yield f"data: {chunk.model_dump_json(exclude_none=False)}\n\n"
        except RepositoryNotFoundError as exc:
            error_chunk = ChatStreamChunk(done=True, error=str(exc))
            yield f"data: {error_chunk.model_dump_json(exclude_none=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error during SSE streaming for repository %s", repository_id)
            error_chunk = ChatStreamChunk(done=True, error=f"Streaming failed: {exc}")
            yield f"data: {error_chunk.model_dump_json(exclude_none=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─── Direct File Chat (no repository needed) ──────────────────────────────────

# Separate router without the /repositories prefix
direct_router = APIRouter(tags=["chat"])


class AttachedFile(BaseModel):
    name: str
    content: str


class DirectChatRequest(BaseModel):
    query: str
    files: List[AttachedFile] = []
    temperature: Optional[float] = None


@direct_router.post(
    "/chat/direct/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream a chat response from uploaded file content (no repository needed)",
    description=(
        "Accepts a question and optional file contents, then streams an LLM answer "
        "using the files as context. No repository connection required."
    ),
)
async def chat_direct_stream(payload: DirectChatRequest) -> StreamingResponse:
    """
    SSE streaming endpoint for direct file-based chat.
    Works without any repository — files are passed as inline context.
    """
    from backend.llm import get_llm_service

    llm = get_llm_service()

    # Build pseudo-chunks from uploaded file contents so we can reuse format_context_blocks
    context_chunks = [
        {
            "content": f.content,
            "metadata": {
                "file_path": f.name,
                "content_type": "code",
            },
        }
        for f in payload.files
    ]

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for token in llm.generate_answer_stream(payload.query, context_chunks):
                chunk = ChatStreamChunk(token=token)
                yield f"data: {chunk.model_dump_json(exclude_none=False)}\n\n"
            # Final done event
            done_chunk = ChatStreamChunk(done=True, citations=[])
            yield f"data: {done_chunk.model_dump_json(exclude_none=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error in direct chat stream")
            error_chunk = ChatStreamChunk(done=True, error=f"Streaming failed: {exc}")
            yield f"data: {error_chunk.model_dump_json(exclude_none=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
