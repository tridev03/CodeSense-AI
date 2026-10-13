"""
RAG Orchestration Service.

Coordinates query embedding, hybrid retrieval (vector + BM25 + RRF + BGE reranking),
context assembly, and LLM grounded answer generation with citations.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import settings
from backend.database import crud
from backend.embeddings import EmbeddingService, get_embedding_service
from backend.llm import LLMService, extract_citations, get_llm_service
from backend.retrieval import VectorStoreService
from backend.retrieval.eval_retrieval import EvalQuery, RetrievalAblationReport, run_retrieval_ablation
from backend.retrieval.hybrid import HybridRetriever, get_bm25_retriever
from backend.schemas.rag import (
    ChatRequest,
    ChatResponse,
    Citation,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from backend.services.repository_service import RepositoryNotFoundError

logger = logging.getLogger(__name__)


class RAGService:
    """
    Orchestrates semantic search, hybrid retrieval, and Q&A over repository code and documents.
    """

    def __init__(
        self,
        db: AsyncSession,
        hybrid_retriever: Optional[HybridRetriever] = None,
        llm_service: Optional[LLMService] = None,
    ):
        self._db = db
        self._hybrid_retriever = hybrid_retriever or HybridRetriever()
        self._llm_service = llm_service or get_llm_service()

    async def _ensure_repository_exists(self, repository_id: uuid.UUID) -> None:
        """Verify the repository exists in database."""
        repo = await crud.get_repository(self._db, repository_id)
        if repo is None:
            raise RepositoryNotFoundError(
                f"Repository with id={repository_id} not found."
            )

    async def search(
        self, repository_id: uuid.UUID, request: SearchRequest
    ) -> SearchResponse:
        """
        Execute multi-stage code and documentation search.
        """
        await self._ensure_repository_exists(repository_id)

        # Build metadata filters
        filters: Dict[str, Any] = {}
        if request.language:
            filters["language"] = request.language.lower()
        if request.content_type:
            filters["content_type"] = request.content_type.lower()

        mode = request.retrieval_mode or settings.RETRIEVAL_MODE
        use_reranker = request.use_reranker if request.use_reranker is not None else True

        # Multi-stage hybrid retrieval offloaded to worker thread (REL-03)
        hits = await asyncio.to_thread(
            self._hybrid_retriever.retrieve,
            repository_id=str(repository_id),
            query=request.query,
            mode=mode,
            top_k=request.top_k,
            filters=filters or None,
            use_reranker=use_reranker,
        )

        # Map to search response items
        results: List[SearchResultItem] = []
        for hit in hits:
            meta = hit.get("metadata", {})
            file_path = meta.get("file_path", "")

            # If path filter provided, filter substring in memory if needed
            if request.file_path and request.file_path.lower() not in file_path.lower():
                continue

            results.append(
                SearchResultItem(
                    chunk_id=hit.get("id", ""),
                    file_path=file_path,
                    content_type=meta.get("content_type", "code"),
                    content=hit.get("content", ""),
                    score=float(hit.get("score", 0.0)),
                    language=meta.get("language"),
                    start_line=meta.get("start_line"),
                    end_line=meta.get("end_line"),
                    symbol_type=meta.get("symbol_type"),
                    class_name=meta.get("class_name"),
                    function_name=meta.get("function_name"),
                    context_header=meta.get("context_header"),
                    section_title=meta.get("section_title"),
                    rerank_score=hit.get("rerank_score"),
                    retriever=hit.get("retriever"),
                )
            )

        return SearchResponse(
            query=request.query,
            repository_id=str(repository_id),
            retrieval_mode=mode,
            total_results=len(results),
            results=results,
        )

    async def chat(
        self, repository_id: uuid.UUID, request: ChatRequest
    ) -> ChatResponse:
        """
        Answer questions about the codebase using grounded hybrid retrieval and LLM synthesis.
        """
        await self._ensure_repository_exists(repository_id)

        mode = request.retrieval_mode or settings.RETRIEVAL_MODE
        use_reranker = request.use_reranker if request.use_reranker is not None else True

        # 1. Retrieve top-k context chunks using multi-stage hybrid retrieval on worker thread (REL-03)
        chunks = await asyncio.to_thread(
            self._hybrid_retriever.retrieve,
            repository_id=str(repository_id),
            query=request.query,
            mode=mode,
            top_k=request.top_k,
            filters=request.filters,
            use_reranker=use_reranker,
        )

        # 2. Synthesize answer with LLM
        answer, tokens_used = await self._llm_service.generate_answer(
            request.query, chunks
        )

        # 3. Extract citations
        citations = []
        if request.include_citations:
            citations = extract_citations(chunks, answer)

        return ChatResponse(
            query=request.query,
            answer=answer,
            repository_id=str(repository_id),
            retrieval_mode=mode,
            citations=citations,
            model=self._llm_service.model,
            tokens_used=tokens_used,
        )

    async def chat_stream(
        self, repository_id: uuid.UUID, request: ChatRequest
    ):
        """
        Stream an answer token-by-token.

        Performs retrieval synchronously first, then delegates to the LLM
        service's async generator.  Yields tuples of:
          ("token", str)   – a text delta
          ("done", List[Citation])  – final signal with citations
        Raises exceptions on retrieval failures so the caller can emit an
        SSE error event.
        """
        await self._ensure_repository_exists(repository_id)

        mode = request.retrieval_mode or settings.RETRIEVAL_MODE
        use_reranker = request.use_reranker if request.use_reranker is not None else True

        # 1. Retrieve context (same as non-streaming path)
        chunks = await asyncio.to_thread(
            self._hybrid_retriever.retrieve,
            repository_id=str(repository_id),
            query=request.query,
            mode=mode,
            top_k=request.top_k,
            filters=request.filters,
            use_reranker=use_reranker,
        )

        # 2. Build citations eagerly (based on retrieved chunks, not the answer text)
        citations = []
        if request.include_citations:
            citations = extract_citations(chunks, "")

        # 3. Stream LLM tokens
        async for token in self._llm_service.generate_answer_stream(request.query, chunks):
            yield ("token", token)

        yield ("done", citations)

    async def evaluate_retrieval(
        self,
        repository_id: uuid.UUID,
        queries: List[EvalQuery],
        *,
        k: int = 5,
    ) -> RetrievalAblationReport:
        """
        Run retrieval ablation evaluation across the repository on worker thread (REL-03).
        """
        await self._ensure_repository_exists(repository_id)
        return await asyncio.to_thread(
            run_retrieval_ablation,
            self._hybrid_retriever,
            str(repository_id),
            queries,
            k=k,
        )
