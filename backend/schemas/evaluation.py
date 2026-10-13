"""
Pydantic schemas for RAG Generation and LLM Evaluation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GenerationEvalRequest(BaseModel):
    """Request body for evaluating generation quality."""
    num_questions: int = Field(default=5, ge=1, le=50, description="Number of evaluation questions to benchmark")
    retrieval_mode: str = Field(default="hybrid", description="Retrieval mode: hybrid | vector_only | bm25_only")
    top_k: int = Field(default=5, ge=1, le=20, description="Top K context chunks retrieved per question")
    use_reranker: bool = Field(default=True, description="Whether to apply cross-encoder reranking")
    custom_questions: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Optional list of custom {'question': ..., 'ground_truth': ...} pairs",
    )


class MetricScores(BaseModel):
    """Aggregate metric scores."""
    faithfulness: float = Field(ge=0.0, le=1.0, description="Fraction of answer grounded in context (higher is better)")
    answer_relevance: float = Field(ge=0.0, le=1.0, description="Relevance of answer to question (higher is better)")
    context_recall: float = Field(ge=0.0, le=1.0, description="Recall of ground truth in retrieved context (higher is better)")
    context_precision: float = Field(ge=0.0, le=1.0, description="Precision of context chunks (higher is better)")
    hallucination_rate: float = Field(ge=0.0, le=1.0, description="Fraction of ungrounded sentences (lower is better)")


class QuestionEvaluationItem(BaseModel):
    """Evaluation result for an individual question."""
    question: str
    ground_truth: Optional[str] = None
    generated_answer: str
    source_file: Optional[str] = None
    retrieved_chunks_count: int
    scores: MetricScores


class GenerationEvalReport(BaseModel):
    """Full Generation Evaluation Report."""
    repository_id: str
    retrieval_mode: str
    model: str
    num_questions: int
    aggregate_scores: MetricScores
    per_question: List[QuestionEvaluationItem]
    markdown_report: str
    evaluated_at: str
