"""
Evaluation Runner for RAG Generation and Answer Quality.

Coordinates:
1. Synthetic dataset creation from repository chunks (or loading custom evaluation pairs).
2. Multi-stage hybrid retrieval for each test question.
3. LLM answer generation with citation extraction.
4. Comprehensive metric computation (faithfulness, answer relevance, context recall, context precision, hallucination rate).
5. Aggregation into structured GenerationEvalReport.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Sequence

from backend.evaluation.metrics import (
    compute_answer_relevance,
    compute_context_precision,
    compute_context_recall,
    compute_faithfulness,
    compute_hallucination_rate,
)
from backend.evaluation.report import format_markdown_eval_report
from backend.evaluation.synthetic import SyntheticQAPair, generate_synthetic_qa_from_chunks
from backend.llm import LLMService, get_llm_service
from backend.retrieval.hybrid import HybridRetriever
from backend.schemas.evaluation import (
    GenerationEvalReport,
    GenerationEvalRequest,
    MetricScores,
    QuestionEvaluationItem,
)

logger = logging.getLogger(__name__)


class GenerationEvaluator:
    """
    Evaluates end-to-end RAG answer quality across repository questions.
    """

    def __init__(
        self,
        hybrid_retriever: Optional[HybridRetriever] = None,
        llm_service: Optional[LLMService] = None,
    ):
        self._retriever = hybrid_retriever or HybridRetriever()
        self._llm = llm_service or get_llm_service()

    async def evaluate_repository(
        self,
        repository_id: str,
        request: GenerationEvalRequest,
        cached_chunks: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> GenerationEvalReport:
        """
        Run generation quality evaluation over synthetic or custom questions.
        """
        logger.info(
            "Starting generation evaluation for repo=%s questions=%d mode=%s",
            repository_id,
            request.num_questions,
            request.retrieval_mode,
        )

        qa_pairs: List[SyntheticQAPair] = []

        # 1. Custom QA pairs provided in request
        if request.custom_questions:
            for item in request.custom_questions[: request.num_questions]:
                qa_pairs.append(
                    SyntheticQAPair(
                        question=item.get("question", ""),
                        ground_truth=item.get("ground_truth", ""),
                        source_file=item.get("source_file", "custom"),
                        symbol_name=item.get("symbol_name"),
                        content_type="custom",
                    )
                )

        # 2. Generate synthetic QA pairs from indexed chunks
        if not qa_pairs:
            chunks = list(cached_chunks or [])
            if not chunks:
                # Retrieve representative sample chunks from the repository
                sample_hits = self._retriever.retrieve(
                    repository_id=repository_id,
                    query="class function module architecture implementation",
                    mode=request.retrieval_mode,
                    top_k=max(request.num_questions * 3, 15),
                    use_reranker=False,
                )
                chunks = sample_hits

            if chunks:
                qa_pairs = generate_synthetic_qa_from_chunks(
                    chunks, max_questions=request.num_questions
                )

        # Fallback if no chunks found
        if not qa_pairs:
            qa_pairs = [
                SyntheticQAPair(
                    question="What does this repository provide and how is it structured?",
                    ground_truth="The repository contains software engineering modules and components.",
                    source_file="README.md",
                    content_type="markdown",
                )
            ]

        question_items: List[QuestionEvaluationItem] = []
        faithfulness_scores: List[float] = []
        relevance_scores: List[float] = []
        recall_scores: List[float] = []
        precision_scores: List[float] = []
        hallucination_scores: List[float] = []

        for pair in qa_pairs:
            # 1. Retrieve context chunks for question
            context_chunks = self._retriever.retrieve(
                repository_id=repository_id,
                query=pair.question,
                mode=request.retrieval_mode,
                top_k=request.top_k,
                use_reranker=request.use_reranker,
            )

            # 2. Generate answer
            answer, _ = await self._llm.generate_answer(pair.question, context_chunks)

            # 3. Compute Metrics
            f_score = compute_faithfulness(answer, context_chunks)
            r_score = compute_answer_relevance(pair.question, answer)
            rec_score = compute_context_recall(pair.ground_truth, context_chunks)
            p_score = compute_context_precision(pair.ground_truth, context_chunks)
            h_score = compute_hallucination_rate(answer, context_chunks)

            faithfulness_scores.append(f_score)
            relevance_scores.append(r_score)
            recall_scores.append(rec_score)
            precision_scores.append(p_score)
            hallucination_scores.append(h_score)

            item_scores = MetricScores(
                faithfulness=f_score,
                answer_relevance=r_score,
                context_recall=rec_score,
                context_precision=p_score,
                hallucination_rate=h_score,
            )

            question_items.append(
                QuestionEvaluationItem(
                    question=pair.question,
                    ground_truth=pair.ground_truth,
                    generated_answer=answer,
                    source_file=pair.source_file,
                    retrieved_chunks_count=len(context_chunks),
                    scores=item_scores,
                )
            )

        # 4. Compute Aggregate Scores
        n = len(question_items) or 1
        agg_scores = MetricScores(
            faithfulness=sum(faithfulness_scores) / n,
            answer_relevance=sum(relevance_scores) / n,
            context_recall=sum(recall_scores) / n,
            context_precision=sum(precision_scores) / n,
            hallucination_rate=sum(hallucination_scores) / n,
        )

        # 5. Format Markdown Report
        md_report = format_markdown_eval_report(
            repository_id=repository_id,
            retrieval_mode=request.retrieval_mode,
            model=self._llm.model,
            aggregate_scores=agg_scores,
            per_question=question_items,
        )

        return GenerationEvalReport(
            repository_id=repository_id,
            retrieval_mode=request.retrieval_mode,
            model=self._llm.model,
            num_questions=len(question_items),
            aggregate_scores=agg_scores,
            per_question=question_items,
            markdown_report=md_report,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
