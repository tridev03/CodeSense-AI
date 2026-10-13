"""
Specialized retrieval tools for the Agentic RAG workflow.

Each tool is a plain callable (not a LangChain Tool) that wraps our existing
HybridRetriever and Git extractor services.  This keeps tools fast, testable,
and free of framework dependencies.

Tools:
    search_code          — Hybrid retrieval focused on code symbols & definitions
    search_docs          — Hybrid retrieval filtered to documentation & markdown
    search_git_history   — Retrieval filtered to git_history content type
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.retrieval.hybrid import HybridRetriever

logger = logging.getLogger(__name__)


def search_code(
    retriever: HybridRetriever,
    repository_id: str,
    query: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search for code symbols, function definitions, class implementations.

    Uses hybrid retrieval (vector + BM25 + RRF + reranker) with a broad filter
    that includes code, config, and generic content types — everything that is
    NOT docs-only or git history.
    """
    logger.info("Tool search_code | repo=%s | query=%r", repository_id, query)

    chunks = retriever.retrieve(
        repository_id=repository_id,
        query=query,
        mode="hybrid",
        top_k=top_k,
        filters=None,           # no content_type filter — code chunks dominate by relevance
        use_reranker=True,
    )

    # Post-filter: prefer code/config chunks (exclude git history which has its own tool)
    code_chunks = [
        c for c in chunks
        if c.get("metadata", {}).get("content_type", "") != "git_history"
        or c.get("content_type", "") != "git_history"
    ]
    return code_chunks or chunks   # fallback to all chunks if filtering eliminates everything


def search_docs(
    retriever: HybridRetriever,
    repository_id: str,
    query: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search for documentation, README files, architectural notes, and Markdown guides.

    Applies a content_type filter to surface markdown and documentation chunks first,
    then falls back to vector-only mode for broader coverage.
    """
    logger.info("Tool search_docs | repo=%s | query=%r", repository_id, query)

    # Try filtered retrieval for markdown/documentation
    chunks = retriever.retrieve(
        repository_id=repository_id,
        query=query,
        mode="hybrid",
        top_k=top_k,
        filters={"content_type": "markdown"},
        use_reranker=True,
    )

    if not chunks:
        # Fallback: unfiltered vector search — docs often mixed with code in small repos
        chunks = retriever.retrieve(
            repository_id=repository_id,
            query=query,
            mode="vector_only",
            top_k=top_k,
            filters=None,
            use_reranker=False,
        )
        chunks = [c for c in chunks if c.get("content_type", "") != "git_history"]

    return chunks


def search_git_history(
    retriever: HybridRetriever,
    repository_id: str,
    query: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search commit history, diff changes, author attributions, and temporal events.

    Applies a git_history content_type filter to target commit chunks specifically.
    Falls back to BM25 keyword search if semantic retrieval returns nothing (commit
    messages are short and keyword-dense).
    """
    logger.info("Tool search_git_history | repo=%s | query=%r", repository_id, query)

    # Primary: semantic search filtered to git history
    chunks = retriever.retrieve(
        repository_id=repository_id,
        query=query,
        mode="hybrid",
        top_k=top_k,
        filters={"content_type": "git_history"},
        use_reranker=False,         # reranker less effective on short commit messages
    )

    if not chunks:
        # Fallback: unfiltered BM25 for keyword-heavy commit message matching
        chunks = retriever.retrieve(
            repository_id=repository_id,
            query=query,
            mode="bm25_only",
            top_k=top_k,
            filters=None,
            use_reranker=False,
        )
        chunks = [
            c for c in chunks
            if c.get("metadata", {}).get("content_type") == "git_history"
            or c.get("content_type") == "git_history"
        ]

    return chunks


# Registry mapping tool name → callable for use by the graph executor
TOOL_REGISTRY = {
    "search_code": search_code,
    "search_docs": search_docs,
    "search_git_history": search_git_history,
}


def run_tool(
    tool_name: str,
    retriever: HybridRetriever,
    repository_id: str,
    query: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Dispatch a named tool call, returning retrieved chunks.

    Raises KeyError if tool_name is not in TOOL_REGISTRY.
    """
    tool_fn = TOOL_REGISTRY[tool_name]
    return tool_fn(retriever, repository_id, query, top_k=top_k)
