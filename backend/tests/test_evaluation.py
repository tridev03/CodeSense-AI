"""
Tests for Phase 7: RAG & Generation Evaluation Suite.

Coverage:
  1. test_faithfulness_metric
  2. test_hallucination_rate_metric
  3. test_answer_relevance_metric
  4. test_context_recall_metric
  5. test_context_precision_metric
  6. test_synthetic_qa_generation_from_chunks
  7. test_generation_evaluator_runner
  8. test_evaluate_generation_endpoint_200
  9. test_evaluate_generation_endpoint_404
"""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient

from backend.evaluation.metrics import (
    compute_answer_relevance,
    compute_context_precision,
    compute_context_recall,
    compute_faithfulness,
    compute_hallucination_rate,
)
from backend.evaluation.runner import GenerationEvaluator
from backend.evaluation.synthetic import generate_synthetic_qa_from_chunks
from backend.schemas.evaluation import GenerationEvalRequest


# ─── Unit Tests: Metric Computations ─────────────────────────────────────────


def test_faithfulness_metric():
    """Faithfulness score is 1.0 when statements are supported by context and low when ungrounded."""
    context = [
        {"content": "FastAPI is a modern web framework for Python based on standard type hints."},
        {"content": "It provides automatic interactive API documentation via Swagger UI."},
    ]

    # Grounded answer
    grounded_answer = "FastAPI is a Python web framework that uses type hints and provides Swagger UI."
    score_grounded = compute_faithfulness(grounded_answer, context)
    assert score_grounded >= 0.8, f"Expected high faithfulness, got {score_grounded}"

    # Ungrounded answer (hallucination)
    ungrounded_answer = "Quantum computing uses superconducting qubits to perform calculations in outer space."
    score_ungrounded = compute_faithfulness(ungrounded_answer, context)
    assert score_ungrounded <= 0.2, f"Expected low faithfulness, got {score_ungrounded}"


def test_hallucination_rate_metric():
    """Hallucination rate is the inverse of faithfulness."""
    context = [{"content": "PostgreSQL is an open-source object-relational database system."}]
    answer = "PostgreSQL is an open-source database system."

    f_score = compute_faithfulness(answer, context)
    h_score = compute_hallucination_rate(answer, context)
    assert abs((f_score + h_score) - 1.0) < 1e-5


def test_answer_relevance_metric():
    """Relevant answers score high while off-topic answers score low."""
    question = "How do I authenticate users with JWT in this service?"
    relevant_answer = "Users are authenticated by verifying the JWT bearer token with the secret key."
    irrelevant_answer = "The weather in Seattle is rainy and cloudy today."

    score_rel = compute_answer_relevance(question, relevant_answer)
    score_irrel = compute_answer_relevance(question, irrelevant_answer)

    assert score_rel > 0.4, f"Expected good relevance, got {score_rel}"
    assert score_irrel < 0.2, f"Expected near zero relevance, got {score_irrel}"


def test_context_recall_metric():
    """Context recall measures whether the ground truth is covered by retrieved chunks."""
    ground_truth = "The session is initialized using async_sessionmaker and commits transactions."
    context = [
        {"content": "Database sessions are created via async_sessionmaker bound to the async engine."},
        {"content": "All database writes perform transactions and commit upon completion."},
    ]

    score = compute_context_recall(ground_truth, context)
    assert score >= 0.8, f"Expected high recall, got {score}"


def test_context_precision_metric():
    """Context precision ranks relevant chunks higher than irrelevant ones."""
    ground_truth = "JWT tokens are verified with HMAC SHA256."
    context_good = [
        {"content": "JWT tokens are signed and verified using HMAC SHA256."},
        {"content": "Random irrelevant background logs."},
    ]
    context_bad = [
        {"content": "Random irrelevant background logs."},
        {"content": "JWT tokens are signed and verified using HMAC SHA256."},
    ]

    p_good = compute_context_precision(ground_truth, context_good)
    p_bad = compute_context_precision(ground_truth, context_bad)

    assert p_good >= p_bad, f"Expected p_good ({p_good}) >= p_bad ({p_bad})"


# ─── Unit Tests: Synthetic Dataset Generation ─────────────────────────────────


def test_synthetic_qa_generation_from_chunks():
    """Synthetic QA generator creates varied questions for functions, classes, docs, and git commits."""
    chunks = [
        {
            "id": "chunk-1",
            "content": "def authenticate_user(token: str):\n    return jwt.decode(token, key='secret')",
            "metadata": {
                "file_path": "backend/auth.py",
                "function_name": "authenticate_user",
                "content_type": "code",
            },
        },
        {
            "id": "chunk-2",
            "content": "class DatabaseConnection:\n    def connect(self): pass",
            "metadata": {
                "file_path": "backend/db.py",
                "class_name": "DatabaseConnection",
                "content_type": "code",
            },
        },
        {
            "id": "chunk-3",
            "content": "# Deployment Guide\nTo deploy with Docker run docker compose up.",
            "metadata": {
                "file_path": "docs/deploy.md",
                "section_title": "Deployment Guide",
                "content_type": "markdown",
            },
        },
        {
            "id": "chunk-4",
            "content": "commit a1b2c3d\nAuthor: dev <dev@example.com>\nDate: 2026-09-30\nRefactor auth flow",
            "metadata": {
                "file_path": "git/history",
                "commit_hash": "a1b2c3d",
                "commit_author": "dev",
                "content_type": "git_history",
            },
        },
    ]

    qa_pairs = generate_synthetic_qa_from_chunks(chunks, max_questions=10)
    assert len(qa_pairs) == 4

    types = [pair.content_type for pair in qa_pairs]
    assert "code" in types
    assert "markdown" in types
    assert "git_history" in types

    for p in qa_pairs:
        assert len(p.question) > 10
        assert len(p.ground_truth) > 10
        assert p.source_file is not None


# ─── Integration Tests: Evaluator & API Route ─────────────────────────────────


@pytest.mark.asyncio
async def test_generation_evaluator_runner():
    """Evaluator generates a complete GenerationEvalReport with valid aggregate and per-question metrics."""
    evaluator = GenerationEvaluator()
    sample_chunks = [
        {
            "id": "c1",
            "content": "def calculate_total(items): return sum(item.price for item in items)",
            "metadata": {
                "file_path": "services/cart.py",
                "function_name": "calculate_total",
                "content_type": "code",
            },
        }
    ]

    req = GenerationEvalRequest(num_questions=1, retrieval_mode="hybrid", top_k=2)
    report = await evaluator.evaluate_repository(
        repository_id=str(uuid.uuid4()),
        request=req,
        cached_chunks=sample_chunks,
    )

    assert report.num_questions == 1
    assert 0.0 <= report.aggregate_scores.faithfulness <= 1.0
    assert 0.0 <= report.aggregate_scores.answer_relevance <= 1.0
    assert 0.0 <= report.aggregate_scores.context_recall <= 1.0
    assert 0.0 <= report.aggregate_scores.context_precision <= 1.0
    assert 0.0 <= report.aggregate_scores.hallucination_rate <= 1.0
    assert len(report.markdown_report) > 50


@pytest.mark.asyncio
async def test_evaluate_generation_endpoint_200(client: AsyncClient):
    """POST /api/v1/repositories/{id}/evaluate-generation returns 200 with complete report."""
    create_resp = await client.post(
        "/api/v1/repositories",
        json={"url": "https://github.com/eval-test/sample-repo"},
    )
    assert create_resp.status_code == 201
    repo_id = create_resp.json()["id"]

    response = await client.post(
        f"/api/v1/repositories/{repo_id}/evaluate-generation",
        json={
            "num_questions": 2,
            "retrieval_mode": "hybrid",
            "top_k": 3,
            "custom_questions": [
                {
                    "question": "How is authentication handled?",
                    "ground_truth": "Authentication is handled via JWT tokens.",
                    "source_file": "backend/auth.py",
                }
            ],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["repository_id"] == repo_id
    assert "aggregate_scores" in data
    assert "faithfulness" in data["aggregate_scores"]
    assert "answer_relevance" in data["aggregate_scores"]
    assert "context_recall" in data["aggregate_scores"]
    assert "markdown_report" in data
    assert len(data["per_question"]) == 1


@pytest.mark.asyncio
async def test_evaluate_generation_endpoint_404(client: AsyncClient):
    """POST /api/v1/repositories/{id}/evaluate-generation returns 404 for unknown repo."""
    fake_id = str(uuid.uuid4())
    response = await client.post(
        f"/api/v1/repositories/{fake_id}/evaluate-generation",
        json={"num_questions": 2},
    )
    assert response.status_code == 404


def test_load_curated_benchmark_dataset():
    """Verify loading curated evaluation benchmark queries."""
    from backend.retrieval.eval_retrieval import load_curated_benchmark_dataset
    queries = load_curated_benchmark_dataset()
    assert len(queries) >= 5
    assert all(q.query and (q.expected_files or q.expected_chunk_ids) for q in queries)

