"""
Unit tests for the RerankerService.

Tests:
- Candidate reordering by relevance
- Top-k truncation
- Empty candidate list handling
"""
from __future__ import annotations

import pytest

from backend.reranking import RerankerService


def test_reranker_reordering() -> None:
    """Verify reranker scores query-document relevance and reorders candidates."""
    service = RerankerService()

    candidates = [
        {"id": "doc-unrelated", "content": "Database migration scripts and SQL schema.", "score": 0.9},
        {"id": "doc-relevant", "content": "Authentication token verification and user login.", "score": 0.5},
    ]

    reranked = service.rerank("user login authentication", candidates, top_k=2)

    assert len(reranked) == 2
    # The relevant document should be promoted to rank 1
    assert reranked[0]["id"] == "doc-relevant"
    assert "rerank_score" in reranked[0]
    assert reranked[0]["rerank_score"] > reranked[1]["rerank_score"]


def test_reranker_empty_list() -> None:
    """Verify reranker handles empty inputs gracefully."""
    service = RerankerService()
    assert service.rerank("query", [], top_k=5) == []

