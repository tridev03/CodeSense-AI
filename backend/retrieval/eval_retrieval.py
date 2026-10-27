"""
Retrieval Evaluation & Ablation Engine.

Evaluates retrieval quality using standard Information Retrieval (IR) metrics:
- Recall@K: Proportion of relevant chunks retrieved in top K.
- MRR@K (Mean Reciprocal Rank): Position of the first relevant chunk.
- nDCG@K (Normalized Discounted Cumulative Gain): Graded ranking quality.
- HitRate@K: Whether at least one relevant chunk was retrieved in top K.

Compares 4 retrieval strategies in an ablation benchmark:
1. Vector Only
2. BM25 Only
3. Hybrid (Vector + BM25 with Reciprocal Rank Fusion)
4. Hybrid + Reranking (Vector + BM25 RRF + BGE Cross-Encoder Reranker)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.retrieval.hybrid import HybridRetriever


class EvalQuery(BaseModel):
    """
    A single evaluation question with expected ground-truth relevant chunk IDs or file paths.
    """
    query: str
    expected_chunk_ids: Optional[List[str]] = Field(default_factory=list)
    expected_files: Optional[List[str]] = Field(default_factory=list)


class StrategyMetrics(BaseModel):
    """
    Aggregated evaluation metrics for a specific retrieval strategy.
    """
    strategy: str
    recall_at_k: float
    mrr_at_k: float
    ndcg_at_k: float
    hit_rate_at_k: float
    avg_latency_ms: float = 0.0


class RetrievalAblationReport(BaseModel):
    """
    Complete ablation benchmark report comparing retrieval strategies.
    """
    repository_id: str
    k: int
    num_queries: int
    strategies: List[StrategyMetrics]
    markdown_table: str


# ─── IR Metrics Calculation Functions ─────────────────────────────────────────


def compute_hit_rate(retrieved_ids: List[str], relevant_ids: set) -> float:
    """HitRate@K: 1.0 if at least one relevant document is in retrieved, else 0.0."""
    if not relevant_ids:
        return 0.0
    return 1.0 if any(rid in relevant_ids for rid in retrieved_ids) else 0.0


def compute_recall(retrieved_ids: List[str], relevant_ids: set) -> float:
    """Recall@K: |retrieved ∩ relevant| / |relevant|."""
    if not relevant_ids:
        return 0.0
    hits = sum(1 for rid in retrieved_ids if rid in relevant_ids)
    return hits / len(relevant_ids)


def compute_mrr(retrieved_ids: List[str], relevant_ids: set) -> float:
    """MRR@K: 1 / rank of the first relevant document, or 0.0 if not found."""
    if not relevant_ids:
        return 0.0
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_ids:
            return 1.0 / rank
    return 0.0


def compute_ndcg(retrieved_ids: List[str], relevant_ids: set, k: int) -> float:
    """nDCG@K: DCG@K / IDCG@K with binary relevance."""
    if not relevant_ids or not retrieved_ids:
        return 0.0

    dcg = 0.0
    for rank, rid in enumerate(retrieved_ids[:k], start=1):
        if rid in relevant_ids:
            dcg += 1.0 / math.log2(rank + 1)

    # Ideal DCG: all relevant documents ranked at the very top
    idcg = 0.0
    ideal_hits = min(len(relevant_ids), k)
    for rank in range(1, ideal_hits + 1):
        idcg += 1.0 / math.log2(rank + 1)

    return (dcg / idcg) if idcg > 0.0 else 0.0


# ─── Ablation Benchmark Runner ────────────────────────────────────────────────


def is_chunk_relevant(chunk: Dict[str, Any], query: EvalQuery) -> bool:
    """
    Check if a retrieved chunk matches either expected chunk IDs or expected file paths.
    """
    chunk_id = chunk.get("id")
    if query.expected_chunk_ids and chunk_id in query.expected_chunk_ids:
        return True

    meta = chunk.get("metadata", {})
    file_path = meta.get("file_path", chunk.get("file_path", ""))
    if query.expected_files and any(ef in file_path for ef in query.expected_files):
        return True

    return False


def run_retrieval_ablation(
    hybrid_retriever: HybridRetriever,
    repository_id: str,
    eval_queries: List[EvalQuery],
    *,
    k: int = 5,
) -> RetrievalAblationReport:
    """
    Run an ablation study comparing 4 retrieval strategies across the evaluation dataset.

    Strategies compared:
    1. vector_only: Pure dense vector search
    2. bm25_only: Pure sparse keyword search
    3. hybrid_no_rerank: Vector + BM25 fused with RRF (no reranker)
    4. hybrid_with_rerank: Vector + BM25 RRF + BGE Cross-Encoder Reranker
    """
    strategies_config = [
        {"name": "Vector Only", "mode": "vector_only", "use_reranker": False},
        {"name": "BM25 Only", "mode": "bm25_only", "use_reranker": False},
        {"name": "Hybrid (RRF)", "mode": "hybrid", "use_reranker": False},
        {"name": "Hybrid + Reranking (BGE)", "mode": "hybrid", "use_reranker": True},
    ]

    results_list: List[StrategyMetrics] = []

    for strat in strategies_config:
        recalls = []
        mrrs = []
        ndcgs = []
        hit_rates = []

        for q in eval_queries:
            hits = hybrid_retriever.retrieve(
                repository_id=repository_id,
                query=q.query,
                mode=strat["mode"],
                top_k=k,
                use_reranker=strat["use_reranker"],
            )

            # Determine relevant items for this query
            # We track relevant items by ID
            retrieved_ids = [h.get("id", "") for h in hits]
            relevant_ids = set()

            for h in hits:
                if is_chunk_relevant(h, q):
                    relevant_ids.add(h.get("id", ""))

            # If expected_chunk_ids provided, merge them
            if q.expected_chunk_ids:
                relevant_ids.update(q.expected_chunk_ids)

            hit_rates.append(compute_hit_rate(retrieved_ids, relevant_ids))
            recalls.append(compute_recall(retrieved_ids, relevant_ids))
            mrrs.append(compute_mrr(retrieved_ids, relevant_ids))
            ndcgs.append(compute_ndcg(retrieved_ids, relevant_ids, k))

        num_q = max(len(eval_queries), 1)
        metrics = StrategyMetrics(
            strategy=strat["name"],
            recall_at_k=round(sum(recalls) / num_q, 4),
            mrr_at_k=round(sum(mrrs) / num_q, 4),
            ndcg_at_k=round(sum(ndcgs) / num_q, 4),
            hit_rate_at_k=round(sum(hit_rates) / num_q, 4),
        )
        results_list.append(metrics)

    # Format Markdown Table
    lines = [
        f"### Retrieval Ablation Benchmark (K={k}, Queries={len(eval_queries)})\n",
        "| Strategy | Recall@K | MRR@K | nDCG@K | Hit Rate@K |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]
    for s in results_list:
        lines.append(
            f"| **{s.strategy}** | {s.recall_at_k:.4f} | {s.mrr_at_k:.4f} | {s.ndcg_at_k:.4f} | {s.hit_rate_at_k:.4f} |"
        )
    markdown_table = "\n".join(lines)

    return RetrievalAblationReport(
        repository_id=repository_id,
        k=k,
        num_queries=len(eval_queries),
        strategies=results_list,
        markdown_table=markdown_table,
    )


def load_curated_benchmark_dataset(dataset_path: Optional[str] = None) -> List[EvalQuery]:
    """
    Load curated evaluation benchmark questions with expected source files and symbols.
    """
    import json
    from pathlib import Path

    if dataset_path:
        p = Path(dataset_path)
    else:
        p = Path(__file__).parent.parent / "evaluation" / "benchmark_dataset.json"

    if not p.exists():
        return []

    with open(p, "r", encoding="utf-8") as f:
        items = json.load(f)

    return [
        EvalQuery(
            query=item["query"],
            expected_files=item.get("expected_files", []),
            expected_chunk_ids=item.get("expected_chunk_ids", []),
        )
        for item in items
    ]


