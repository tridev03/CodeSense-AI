"""
Semantic search and retrieval evaluation endpoints.

Allows searching repository code and documentation using hybrid retrieval
(vector + BM25 + RRF + BGE reranking) and benchmarking retrieval strategies.
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.retrieval.eval_retrieval import EvalQuery, RetrievalAblationReport
from backend.schemas.rag import AblationRequest, SearchRequest, SearchResponse
from backend.services.rag_service import RAGService
from backend.services.repository_service import RepositoryNotFoundError

router = APIRouter(prefix="/repositories", tags=["search"])


def _rag_service(db: AsyncSession = Depends(get_db)) -> RAGService:
    return RAGService(db)


@router.post(
    "/{repository_id}/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Multi-stage search over repository code and docs",
    description="Searches code and documentation using vector search, BM25, or hybrid RRF fusion with BGE reranking.",
)
async def search_repository(
    repository_id: uuid.UUID,
    payload: SearchRequest,
    rag_svc: RAGService = Depends(_rag_service),
) -> SearchResponse:
    try:
        return await rag_svc.search(repository_id, payload)
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{repository_id}/evaluate-retrieval",
    response_model=RetrievalAblationReport,
    status_code=status.HTTP_200_OK,
    summary="Run retrieval ablation study",
    description="Evaluates retrieval quality (Recall@K, MRR@K, nDCG@K, HitRate@K) across Vector, BM25, Hybrid, and Hybrid+Reranker.",
)
async def evaluate_retrieval_endpoint(
    repository_id: uuid.UUID,
    payload: AblationRequest,
    rag_svc: RAGService = Depends(_rag_service),
) -> RetrievalAblationReport:
    try:
        eval_queries = [
            EvalQuery(
                query=q.query,
                expected_chunk_ids=q.expected_chunk_ids,
                expected_files=q.expected_files,
            )
            for q in payload.queries
        ]
        return await rag_svc.evaluate_retrieval(repository_id, eval_queries, k=payload.k)
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
