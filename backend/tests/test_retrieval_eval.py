"""
Unit and integration tests for Retrieval Evaluation and Ablation Engine.

Tests:
- Information Retrieval metrics (Recall@K, MRR@K, nDCG@K, HitRate@K)
- 4-way ablation comparison (Vector vs BM25 vs Hybrid vs Hybrid+Reranker)
- API endpoint: POST /api/v1/repositories/{id}/evaluate-retrieval
"""
from __future__ import annotations

import math
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.retrieval.eval_retrieval import (
    EvalQuery,
    compute_hit_rate,
    compute_mrr,
    compute_ndcg,
    compute_recall,
    run_retrieval_ablation,
)
from backend.retrieval.hybrid import HybridRetriever
from backend.services.repository_service import RepositoryService
from backend.schemas.repository import RepositoryCreate


def test_metric_computations() -> None:
    """Verify standard Information Retrieval metric formulas."""
    relevant = {"doc1", "doc2"}

    # Perfect ranking: [doc1, doc2, doc3]
    retrieved_perfect = ["doc1", "doc2", "doc3"]
    assert compute_hit_rate(retrieved_perfect, relevant) == 1.0
    assert compute_recall(retrieved_perfect, relevant) == 1.0
    assert compute_mrr(retrieved_perfect, relevant) == 1.0  # 1/1 = 1.0
    assert compute_ndcg(retrieved_perfect, relevant, k=3) == 1.0

    # Partial ranking: [doc3, doc1, doc4]
    retrieved_partial = ["doc3", "doc1", "doc4"]
    assert compute_hit_rate(retrieved_partial, relevant) == 1.0
    assert compute_recall(retrieved_partial, relevant) == 0.5  # 1 out of 2
    assert compute_mrr(retrieved_partial, relevant) == 0.5   # 1/2 = 0.5
    assert 0.0 < compute_ndcg(retrieved_partial, relevant, k=3) < 1.0

    # Zero hit ranking: [doc3, doc4, doc5]
    retrieved_zero = ["doc3", "doc4", "doc5"]
    assert compute_hit_rate(retrieved_zero, relevant) == 0.0
    assert compute_recall(retrieved_zero, relevant) == 0.0
    assert compute_mrr(retrieved_zero, relevant) == 0.0
    assert compute_ndcg(retrieved_zero, relevant, k=3) == 0.0


@pytest.fixture
def repo_for_ablation(tmp_path: Path) -> Path:
    """Create a sample repo with multiple code and doc files for evaluation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "class AuthService:\n    def login(self): return True\n",
        encoding="utf-8",
    )
    (src / "database.py").write_text(
        "class DatabasePool:\n    def execute_query(self): return []\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# System Architecture\nExplains security and database layers.\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.asyncio
async def test_ablation_engine_and_endpoint(
    client: AsyncClient, test_db: AsyncSession, repo_for_ablation: Path
) -> None:
    """Run full 4-way retrieval ablation study via service and HTTP endpoint."""
    # 1. Register and index repository
    service = RepositoryService(test_db)
    repo = await service.create_repository(
        RepositoryCreate(url=str(repo_for_ablation), name="Eval Repo")
    )
    job = await service.trigger_indexing(repo.id)
    await service.execute_indexing(repo.id, job.id)

    # 2. Test ablation evaluation endpoint
    eval_payload = {
        "k": 3,
        "queries": [
            {
                "query": "AuthService login",
                "expected_files": ["auth.py"],
            },
            {
                "query": "DatabasePool execute_query",
                "expected_files": ["database.py"],
            },
        ],
    }

    resp = await client.post(
        f"/api/v1/repositories/{repo.id}/evaluate-retrieval",
        json=eval_payload,
    )
    assert resp.status_code == 200
    report = resp.json()

    assert report["repository_id"] == str(repo.id)
    assert report["k"] == 3
    assert report["num_queries"] == 2
    assert len(report["strategies"]) == 4

    strategy_names = [s["strategy"] for s in report["strategies"]]
    assert "Vector Only" in strategy_names
    assert "BM25 Only" in strategy_names
    assert "Hybrid (RRF)" in strategy_names
    assert "Hybrid + Reranking (BGE)" in strategy_names

    # Verify metrics exist for each strategy
    for strat in report["strategies"]:
        assert 0.0 <= strat["recall_at_k"] <= 1.0
        assert 0.0 <= strat["mrr_at_k"] <= 1.0
        assert 0.0 <= strat["ndcg_at_k"] <= 1.0
        assert 0.0 <= strat["hit_rate_at_k"] <= 1.0

    # Verify markdown table was generated
    assert "### Retrieval Ablation Benchmark" in report["markdown_table"]
    assert "| Strategy | Recall@K | MRR@K | nDCG@K | Hit Rate@K |" in report["markdown_table"]

