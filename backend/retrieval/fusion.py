"""
Reciprocal Rank Fusion (RRF) for Hybrid Retrieval.

Merges ranked result sets from dense vector retrieval and sparse BM25 retrieval
into a unified candidate ranking without requiring calibrated score normalization.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def reciprocal_rank_fusion(
    ranked_lists: Dict[str, List[Dict[str, Any]]],
    *,
    k: int = 60,
    weights: Optional[Dict[str, float]] = None,
    top_n: int = 20,
) -> List[Dict[str, Any]]:
    """
    Apply Reciprocal Rank Fusion across multiple ranked retrieval lists.

    Args:
        ranked_lists: Dictionary mapping retriever name (e.g. 'vector', 'bm25')
                      to ranked list of hit dictionaries [{'id': ..., 'content': ..., 'metadata': ...}].
        k: Smoothing constant (standard RRF constant is 60).
        weights: Optional dictionary of weights per retriever name (defaults to 1.0 each).
        top_n: Number of fused candidates to return.

    Returns:
        Deduplicated, merged candidate list sorted descending by RRF score.
    """
    rrf_scores: Dict[str, float] = {}
    doc_store: Dict[str, Dict[str, Any]] = {}
    ranks_by_system: Dict[str, Dict[str, int]] = {}

    weights = weights or {}

    for system_name, hits in ranked_lists.items():
        w = weights.get(system_name, 1.0)
        for rank, hit in enumerate(hits, start=1):
            doc_id = hit["id"]

            if doc_id not in doc_store:
                doc_store[doc_id] = {
                    "id": doc_id,
                    "content": hit.get("content", ""),
                    "metadata": hit.get("metadata", {}),
                }

            # Update RRF score
            rrf_contrib = w / (k + rank)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + rrf_contrib

            # Track rank in this system
            if doc_id not in ranks_by_system:
                ranks_by_system[doc_id] = {}
            ranks_by_system[doc_id][system_name] = rank

    # Assemble fused candidates
    fused_candidates: List[Dict[str, Any]] = []
    for doc_id, score in rrf_scores.items():
        doc = doc_store[doc_id]
        fused_candidates.append(
            {
                "id": doc["id"],
                "score": score,
                "content": doc["content"],
                "metadata": doc["metadata"],
                "ranks": ranks_by_system.get(doc_id, {}),
            }
        )

    # Sort descending by composite RRF score
    fused_candidates.sort(key=lambda x: x["score"], reverse=True)
    return fused_candidates[:top_n]

