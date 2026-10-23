"""
Agent API route.

POST /api/v1/repositories/{repository_id}/agent/query
    Runs the full agentic RAG workflow:
    intent detection → multi-tool retrieval → self-reflection → grounded answer.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.graph import get_agent
from backend.agents.state import make_initial_state
from backend.api.dependencies import get_valid_repository
from backend.database.models import Repository
from backend.schemas.agent import AgentQueryRequest, AgentQueryResponse, AgentToolCallLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])


@router.post(
    "/repositories/{repository_id}/agent/query",
    response_model=AgentQueryResponse,
    summary="Agentic multi-step Q&A",
    description=(
        "Run an autonomous reasoning agent over the repository. "
        "The agent detects query intent, selects and executes specialized tools "
        "(search_code, search_docs, search_git_history), reflects on context quality, "
        "self-corrects if necessary, and generates a grounded answer with citations."
    ),
    status_code=status.HTTP_200_OK,
)
async def agent_query(
    repository_id: uuid.UUID,
    request: AgentQueryRequest,
    repo: Repository = Depends(get_valid_repository),
) -> AgentQueryResponse:
    """
    Agentic Q&A endpoint.

    Raises:
        404 — if the repository does not exist.
        403 — if user lacks tenant access.
        500 — if the agent raises an unexpected error.
    """
    logger.info(
        "Agent query | repo=%s | query=%r | top_k=%d | max_reflections=%d",
        repository_id,
        request.query,
        request.top_k,
        request.max_reflections,
    )

    # Build agent (MockAgent in test mode, LangGraph in production)
    agent = get_agent(top_k=request.top_k)

    # Initialise state
    initial_state = make_initial_state(
        query=request.query,
        repository_id=str(repository_id),
    )

    try:
        final_state = await agent.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Agent workflow failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent encountered an error while processing your query.",
        ) from exc

    # Map agent state → response schema
    tool_call_logs = [
        AgentToolCallLog(
            tool_name=tc["tool_name"],
            query=tc["query"],
            result_count=tc["result_count"],
        )
        for tc in final_state.get("tool_calls", [])
    ]

    citations = final_state.get("citations", []) if request.include_citations else []

    from backend.llm import get_llm_service
    llm = get_llm_service()

    return AgentQueryResponse(
        query=request.query,
        repository_id=str(repository_id),
        intent=final_state.get("intent", "general"),
        answer=final_state.get("final_answer") or "No answer could be generated.",
        citations=citations,
        tool_calls=tool_call_logs,
        reflection_count=final_state.get("reflection_count", 0),
        tokens_used=final_state.get("tokens_used"),
        model=llm.model,
    )
