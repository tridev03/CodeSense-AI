"""
Semantic search and retrieval evaluation endpoints.

Allows searching repository code and documentation using hybrid retrieval
(vector + BM25 + RRF + BGE reranking) and benchmarking retrieval strategies.
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db, get_valid_repository
from backend.database.models import Repository
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
    repo: Repository = Depends(get_valid_repository),
    rag_svc: RAGService = Depends(_rag_service),
) -> SearchResponse:
    return await rag_svc.search(repo.id, payload)


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
    repo: Repository = Depends(get_valid_repository),
    rag_svc: RAGService = Depends(_rag_service),
) -> RetrievalAblationReport:
    eval_queries = [
        EvalQuery(
            query=q.query,
            expected_chunk_ids=q.expected_chunk_ids,
            expected_files=q.expected_files,
        )
        for q in payload.queries
    ]
    return await rag_svc.evaluate_retrieval(repo.id, eval_queries, k=payload.k)
