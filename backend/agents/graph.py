"""
LangGraph StateGraph definition for the Agentic RAG workflow.

Graph topology:
    __start__ → route_query → execute_tools → reflect → [retry or generate] → __end__

The reflect node uses a conditional edge:
    needs_retry=True  → route_query  (max MAX_REFLECTIONS times)
    needs_retry=False → generate     → __end__

For test / offline environments (TESTING=True) a MockAgent is used instead of
building the full LangGraph to avoid heavy imports and keep tests in <2s.
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Dict, Optional

from backend.agents.state import AgentState, make_initial_state
from backend.config.settings import settings
from backend.llm import LLMService, get_llm_service
from backend.retrieval.hybrid import HybridRetriever, get_bm25_retriever

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _should_retry(state: AgentState) -> str:
    """Conditional edge: route after reflect node."""
    if state.get("needs_retry", False):
        return "route_query"
    return "generate_answer"


# ─── Graph Builder ────────────────────────────────────────────────────────────


def build_agent_graph(
    retriever: HybridRetriever,
    llm_service: LLMService,
    top_k: int = 5,
):
    """
    Compile and return a LangGraph StateGraph for agentic RAG.

    Args:
        retriever:   Configured HybridRetriever instance.
        llm_service: Configured LLMService instance.
        top_k:       Number of chunks to retrieve per tool call.

    Returns:
        Compiled LangGraph app (supports .ainvoke()).
    """
    from langgraph.graph import StateGraph, END
    from backend.agents.nodes import (
        route_query,
        execute_tools,
        reflect_on_context,
        generate_answer,
    )

    # Bind injected services to node functions (partial application)
    _execute = partial(execute_tools, retriever=retriever, top_k=top_k)
    _generate = partial(generate_answer, llm_service=llm_service)

    # Wrap the async generate node so LangGraph can call it
    async def _generate_node(state: AgentState) -> Dict[str, Any]:
        return await _generate(state)

    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("route_query", route_query)
    graph.add_node("execute_tools", _execute)
    graph.add_node("reflect", reflect_on_context)
    graph.add_node("generate_answer", _generate_node)

    # Wire edges
    graph.set_entry_point("route_query")
    graph.add_edge("route_query", "execute_tools")
    graph.add_edge("execute_tools", "reflect")
    graph.add_conditional_edges(
        "reflect",
        _should_retry,
        {
            "route_query": "route_query",
            "generate_answer": "generate_answer",
        },
    )
    graph.add_edge("generate_answer", END)

    return graph.compile()


# ─── Mock Agent (used when TESTING=True) ─────────────────────────────────────


class MockAgent:
    """
    Deterministic stand-in agent for test environments.

    Does NOT import LangGraph or call any external services.
    Simulates one tool call + immediate answer generation using LLMService mock.
    """

    def __init__(self, retriever: HybridRetriever, llm_service: LLMService, top_k: int = 5):
        self._retriever = retriever
        self._llm = llm_service
        self._top_k = top_k

    async def ainvoke(self, state: AgentState) -> AgentState:
        from backend.agents.nodes import route_query, execute_tools, reflect_on_context, generate_answer

        # Step 1: route
        state.update(route_query(state))

        # Step 2: execute tools
        state.update(execute_tools(state, retriever=self._retriever, top_k=self._top_k))

        # Step 3: reflect (single pass — mock never retries)
        reflect_result = reflect_on_context(state)
        state.update(reflect_result)
        state["needs_retry"] = False   # Never retry in mock mode

        # Step 4: generate
        gen_result = await generate_answer(state, llm_service=self._llm)
        state.update(gen_result)

        return state


# ─── Agent Factory ────────────────────────────────────────────────────────────


def get_agent(
    retriever: Optional[HybridRetriever] = None,
    llm_service: Optional[LLMService] = None,
    top_k: int = 5,
):
    """
    Return the appropriate agent based on the runtime environment.

    - TESTING=True → MockAgent (no LangGraph, offline-safe, fast)
    - Otherwise    → compiled LangGraph StateGraph
    """
    _retriever = retriever or HybridRetriever()
    _llm = llm_service or get_llm_service()

    if settings.is_testing:
        logger.debug("Agent: using MockAgent (TESTING mode)")
        return MockAgent(_retriever, _llm, top_k=top_k)

    logger.debug("Agent: building LangGraph StateGraph")
    return build_agent_graph(_retriever, _llm, top_k=top_k)
