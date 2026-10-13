"""
Evaluation API route.

POST /api/v1/repositories/{repository_id}/evaluate-generation
    Runs generation quality evaluation (faithfulness, answer relevance, context recall,
    context precision, hallucination rate) over synthetic or custom Q&A pairs.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.database import crud
from backend.evaluation.runner import GenerationEvaluator
from backend.schemas.evaluation import GenerationEvalReport, GenerationEvalRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evaluation"])


@router.post(
    "/repositories/{repository_id}/evaluate-generation",
    response_model=GenerationEvalReport,
    summary="Evaluate RAG Generation Quality",
    description=(
        "Run automated generation quality evaluation across the repository. "
        "Measures Faithfulness, Answer Relevance, Context Recall, Context Precision, "
        "and Hallucination Rate using synthetic or custom test questions."
    ),
    status_code=status.HTTP_200_OK,
)
async def evaluate_generation(
    repository_id: uuid.UUID,
    request: GenerationEvalRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerationEvalReport:
    """
    Evaluate LLM Generation & Answer Quality.

    Raises:
        404 — if repository does not exist.
        500 — if evaluation pipeline encounters an unexpected error.
    """
    repo = await crud.get_repository(db, repository_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repository_id} not found.",
        )

    logger.info(
        "Evaluate generation requested | repo=%s | questions=%d | mode=%s",
        repository_id,
        request.num_questions,
        request.retrieval_mode,
    )

    evaluator = GenerationEvaluator()

    try:
        report = await evaluator.evaluate_repository(
            repository_id=str(repository_id),
            request=request,
        )
        return report
    except Exception as exc:
        logger.exception("Generation evaluation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation evaluation failed: {str(exc)}",
        ) from exc
