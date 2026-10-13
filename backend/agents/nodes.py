"""
LangGraph node functions for the Agentic RAG workflow.

Each node is a pure function:
    input:  AgentState (current)
    output: dict[str, Any] — partial state update

Nodes:
    route_query          Intent detection → tools_to_run list
    execute_tools        Runs each tool and accumulates context_chunks
    reflect_on_context   Quality check → maybe set needs_retry + retry_query
    generate_answer      LLM call → final_answer + citations
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List

from backend.agents.state import AgentState, ToolCall
from backend.agents.tools import run_tool, TOOL_REGISTRY
from backend.llm import LLMService, extract_citations, format_context_blocks
from backend.retrieval.hybrid import HybridRetriever

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_REFLECTIONS = 2         # Hard cap on self-correction cycles
MIN_USEFUL_CHUNKS = 2       # Minimum chunks to consider context "adequate"

# Intent keyword patterns  (ordered — first match wins)
_INTENT_PATTERNS = [
    ("git", re.compile(
        r"\b(commit|diff|author|blame|merge|branch|history|when was|who changed|"
        r"refactor|pull request|release|changelog|version)\b",
        re.IGNORECASE,
    )),
    ("docs", re.compile(
        r"\b(readme|documentation|docs|guide|tutorial|setup|install|architecture|"
        r"design|overview|getting.?started|how to use)\b",
        re.IGNORECASE,
    )),
    ("code", re.compile(
        r"\b(function|class|method|module|import|def |implement|algorithm|"
        r"api|endpoint|route|schema|model|service|util|helper|test)\b",
        re.IGNORECASE,
    )),
]


# ─── Node: Query Router ───────────────────────────────────────────────────────


def route_query(state: AgentState) -> Dict[str, Any]:
    """
    Detect query intent and select which tools to run.

    Rules:
    - "git" intent → [search_git_history, search_code]
    - "docs" intent → [search_docs, search_code]
    - "code" intent → [search_code]
    - "general" intent → [search_code, search_docs, search_git_history]

    On retry (needs_retry=True) the router always falls back to all three tools
    with the reformulated query to maximise recall.
    """
    query = state.get("retry_query") or state["query"]
    is_retry = state.get("needs_retry", False)

    if is_retry:
        intent = "general"
        tools = ["search_code", "search_docs", "search_git_history"]
        logger.info("Router: retry detected — running all tools with query=%r", query)
        return {
            "intent": intent,
            "tools_to_run": tools,
            "needs_retry": False,
        }

    # Match intent
    intent = "general"
    for name, pattern in _INTENT_PATTERNS:
        if pattern.search(query):
            intent = name
            break

    tool_map = {
        "git":     ["search_git_history", "search_code"],
        "docs":    ["search_docs", "search_code"],
        "code":    ["search_code"],
        "general": ["search_code", "search_docs"],
    }
    tools = tool_map[intent]

    logger.info("Router: intent=%s tools=%s query=%r", intent, tools, query)
    return {
        "intent": intent,
        "tools_to_run": tools,
    }


# ─── Node: Tool Executor ──────────────────────────────────────────────────────


def execute_tools(
    state: AgentState,
    retriever: HybridRetriever,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Execute each tool in tools_to_run and accumulate unique context chunks.

    Deduplication is based on (file_path, start_line, end_line) for code chunks
    and commit_hash for git_history chunks.
    """
    query = state.get("retry_query") or state["query"]
    repo_id = state["repository_id"]
    tools = state.get("tools_to_run", [])

    existing_chunks: List[Dict[str, Any]] = list(state.get("context_chunks", []))
    new_tool_calls: List[ToolCall] = []

    # Build dedup key set from already-accumulated chunks
    seen_keys = set()
    for c in existing_chunks:
        meta = c.get("metadata", {})
        commit_hash = meta.get("commit_hash")
        if commit_hash:
            seen_keys.add(f"commit:{commit_hash}")
        else:
            fp = meta.get("file_path", c.get("file_path", ""))
            sl = meta.get("start_line", c.get("start_line"))
            el = meta.get("end_line", c.get("end_line"))
            seen_keys.add(f"{fp}:{sl}:{el}")

    # Run each tool
    for tool_name in tools:
        if tool_name not in TOOL_REGISTRY:
            logger.warning("Unknown tool %r — skipping", tool_name)
            continue

        try:
            chunks = run_tool(tool_name, retriever, repo_id, query, top_k=top_k)
        except Exception as exc:
            logger.error("Tool %r raised %s — skipping", tool_name, exc)
            chunks = []

        new_tool_calls.append(
            ToolCall(tool_name=tool_name, query=query, result_count=len(chunks))
        )

        # Deduplicate before appending
        for c in chunks:
            meta = c.get("metadata", {})
            commit_hash = meta.get("commit_hash")
            if commit_hash:
                key = f"commit:{commit_hash}"
            else:
                fp = meta.get("file_path", c.get("file_path", ""))
                sl = meta.get("start_line", c.get("start_line"))
                el = meta.get("end_line", c.get("end_line"))
                key = f"{fp}:{sl}:{el}"

            if key not in seen_keys:
                seen_keys.add(key)
                existing_chunks.append(c)

    logger.info(
        "Tool executor: %d total unique chunks after %d tool calls",
        len(existing_chunks), len(new_tool_calls),
    )

    return {
        "context_chunks": existing_chunks,
        "tool_calls": list(state.get("tool_calls", [])) + new_tool_calls,
        "retry_query": None,    # Clear retry query after execution
    }


# ─── Node: Reflector ─────────────────────────────────────────────────────────


def reflect_on_context(state: AgentState) -> Dict[str, Any]:
    """
    Assess the quality of retrieved context and decide whether to retry.

    Heuristics:
    1. Too few chunks → reformulate query and retry.
    2. Context appears totally irrelevant (no query terms found) → retry with
       a broader paraphrase.
    3. Max reflections reached → proceed regardless.

    Returns needs_retry=False to proceed to generation, or needs_retry=True
    plus a reformulated retry_query.
    """
    query = state["query"]
    chunks = state.get("context_chunks", [])
    reflection_count = state.get("reflection_count", 0)

    # Hard cap: always generate after MAX_REFLECTIONS retries
    if reflection_count >= MAX_REFLECTIONS:
        logger.info("Reflector: max reflections (%d) reached — proceeding to generation", MAX_REFLECTIONS)
        return {"needs_retry": False}

    # Heuristic 1: not enough chunks
    if len(chunks) < MIN_USEFUL_CHUNKS:
        reformulated = _broaden_query(query, reflection_count)
        logger.info(
            "Reflector: only %d chunks — retry #%d with query=%r",
            len(chunks), reflection_count + 1, reformulated,
        )
        return {
            "needs_retry": True,
            "retry_query": reformulated,
            "reflection_count": reflection_count + 1,
        }

    # Heuristic 2: basic relevance check — at least one substantive query term
    # appears anywhere in the combined chunk content (case-insensitive substring).
    substantive_query_terms = [
        t for t in re.findall(r"\b\w{5,}\b", query.lower())
        if t not in {"which", "where", "about", "their", "there", "these", "those"}
    ]
    combined_content = " ".join(c.get("content", "") for c in chunks[:5]).lower()

    overlap = [t for t in substantive_query_terms if t in combined_content]

    if not overlap and substantive_query_terms and reflection_count == 0:
        reformulated = _broaden_query(query, reflection_count)
        logger.info(
            "Reflector: no keyword overlap — retry with query=%r",
            reformulated,
        )
        return {
            "needs_retry": True,
            "retry_query": reformulated,
            "reflection_count": reflection_count + 1,
        }

    logger.info(
        "Reflector: context adequate (%d chunks, %d overlap terms) — generating answer",
        len(chunks), len(overlap),
    )
    return {"needs_retry": False}


def _broaden_query(query: str, attempt: int) -> str:
    """Simple query broadening: add context-encouraging prefixes."""
    prefixes = [
        f"how does {query} work",
        f"explain {query} in the codebase",
        f"what is the implementation of {query}",
    ]
    return prefixes[min(attempt, len(prefixes) - 1)]


# ─── Node: Answer Generator ───────────────────────────────────────────────────


async def generate_answer(
    state: AgentState,
    llm_service: LLMService,
) -> Dict[str, Any]:
    """
    Generate the final grounded answer using the LLM and accumulated context chunks.

    Returns final_answer, citations, and tokens_used.
    """
    query = state["query"]
    chunks = state.get("context_chunks", [])

    answer, tokens_used = await llm_service.generate_answer(query, chunks)

    # Build citations from chunks that contributed to the answer
    raw_citations = extract_citations(chunks, answer)
    citations = [
        {
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "symbol": c.symbol,
            "snippet": c.snippet,
        }
        for c in raw_citations
    ]

    logger.info(
        "Generator: answer produced (%d chars, %d citations, tokens=%s)",
        len(answer), len(citations), tokens_used,
    )

    return {
        "final_answer": answer,
        "citations": citations,
        "tokens_used": tokens_used,
    }
