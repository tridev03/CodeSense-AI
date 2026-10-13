"""
Unit tests for Reciprocal Rank Fusion (RRF).

Tests:
- Merging two ranked lists
- Items appearing in both systems rank higher than items in only one
- RRF score monotonicity and deduplication
"""
from __future__ import annotations

from backend.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_both_systems_boost() -> None:
    """Verify an item appearing in both systems gets a higher score than an item in only one."""
    vector_results = [
        {"id": "doc-A", "content": "vector first"},
        {"id": "doc-B", "content": "vector second"},
    ]
    bm25_results = [
        {"id": "doc-B", "content": "bm25 first"},
        {"id": "doc-C", "content": "bm25 second"},
    ]

    fused = reciprocal_rank_fusion(
        {"vector": vector_results, "bm25": bm25_results},
        k=60,
    )

    # doc-B appears in both (rank 2 in vector, rank 1 in bm25)
    # score(doc-B) = 1/(60+2) + 1/(60+1) = 0.0161 + 0.0164 = 0.0325
    # score(doc-A) = 1/(60+1) = 0.0164
    assert fused[0]["id"] == "doc-B"
    assert fused[0]["score"] > fused[1]["score"]
    assert len(fused) == 3


def test_rrf_deduplication() -> None:
    """Verify result set is strictly deduplicated."""
    hits1 = [{"id": "d1", "content": "text 1"}, {"id": "d2", "content": "text 2"}]
    hits2 = [{"id": "d1", "content": "text 1"}, {"id": "d3", "content": "text 3"}]

    fused = reciprocal_rank_fusion({"sys1": hits1, "sys2": hits2}, k=60)
    ids = [item["id"] for item in fused]

    assert len(ids) == len(set(ids))
    assert set(ids) == {"d1", "d2", "d3"}

