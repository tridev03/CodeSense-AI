"""
Agent State schema for the LangGraph Agentic RAG workflow.

The AgentState TypedDict is the single shared state that flows through every
node in the graph.  Each node receives the current state, mutates it, and
returns a (partial) dict of updated keys.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class ToolCall(TypedDict):
    """Record of a single tool invocation made by the agent."""
    tool_name: str          # "search_code" | "search_docs" | "search_git_history"
    query: str              # Query string passed to the tool
    result_count: int       # How many chunks were returned


class AgentState(TypedDict):
    """
    Shared mutable state flowing through the LangGraph agent graph.

    Lifecycle:
        1. Initialized at the entry node (router) with the user query.
        2. Tool executor appends chunks to `context_chunks` and logs to `tool_calls`.
        3. Reflector checks quality and sets `needs_retry` / increments `reflection_count`.
        4. Generator consumes `context_chunks` and writes `final_answer`.
    """
    # ── Input ──────────────────────────────────────────────────────────────
    query: str                              # Original user question
    repository_id: str                     # UUID of the repository being queried

    # ── Routing ────────────────────────────────────────────────────────────
    intent: str                             # "code" | "docs" | "git" | "general"
    tools_to_run: List[str]                 # Ordered list of tool names to execute

    # ── Execution ──────────────────────────────────────────────────────────
    tool_calls: List[ToolCall]              # Audit log of all tool calls made
    context_chunks: List[Dict[str, Any]]   # Accumulated retrieved chunks (deduped)

    # ── Reflection ─────────────────────────────────────────────────────────
    reflection_count: int                  # Number of self-correction cycles done
    needs_retry: bool                      # Reflector signals another retrieval round
    retry_query: Optional[str]             # Reformulated query for retry (if any)

    # ── Output ─────────────────────────────────────────────────────────────
    final_answer: Optional[str]            # LLM-generated grounded answer
    citations: List[Dict[str, Any]]        # Structured citation objects
    tokens_used: Optional[int]             # Total tokens consumed


# Default / initial state factory
def make_initial_state(query: str, repository_id: str) -> AgentState:
    """Create a fresh AgentState for a new agent run."""
    return AgentState(
        query=query,
        repository_id=repository_id,
        intent="general",
        tools_to_run=[],
        tool_calls=[],
        context_chunks=[],
        reflection_count=0,
        needs_retry=False,
        retry_query=None,
        final_answer=None,
        citations=[],
        tokens_used=None,
    )
