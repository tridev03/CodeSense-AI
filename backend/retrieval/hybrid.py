"""
Hybrid Retriever combining Dense Vector Search, BM25 Keyword Search, and Reranking.

Pipeline:
1. Dense Retrieval (Qdrant) -> Top-N candidates
2. Sparse Retrieval (BM25)  -> Top-N candidates
3. Candidate Fusion         -> Reciprocal Rank Fusion (RRF)
4. Cross-Encoder Reranker   -> BAAI/bge-reranker-base Top-K
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.config.settings import settings
from backend.embeddings import EmbeddingService, get_embedding_service
from backend.reranking import RerankerService, get_reranker_service
from backend.retrieval import VectorStoreService
from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.fusion import reciprocal_rank_fusion

logger = logging.getLogger(__name__)

_bm25_retriever_instance: Optional[BM25Retriever] = None


def get_bm25_retriever() -> BM25Retriever:
    """Return the singleton BM25Retriever."""
    global _bm25_retriever_instance
    if _bm25_retriever_instance is None:
        _bm25_retriever_instance = BM25Retriever()
    return _bm25_retriever_instance


class HybridRetriever:
    """
    Coordinates dense vector search, BM25 keyword search, RRF fusion, and cross-encoder reranking.
    """

    def __init__(
        self,
        vector_store: Optional[VectorStoreService] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        embedding_service: Optional[EmbeddingService] = None,
        reranker_service: Optional[RerankerService] = None,
    ):
        self._vector_store = vector_store or VectorStoreService()
        self._bm25_retriever = bm25_retriever or get_bm25_retriever()
        self._embedding_service = embedding_service or get_embedding_service()
        self._reranker_service = reranker_service or get_reranker_service()

    def retrieve(
        self,
        repository_id: str,
        query: str,
        *,
        mode: Optional[str] = None,
        top_k: int = 5,
        candidate_pool_size: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        use_reranker: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Execute multi-stage retrieval based on the specified mode.

        Args:
            repository_id: UUID of the repository.
            query: User search query or question.
            mode: 'vector_only' | 'bm25_only' | 'hybrid' (defaults to settings.RETRIEVAL_MODE).
            top_k: Number of final results to return.
            candidate_pool_size: Number of initial candidates to pull from each retriever before fusion.
            filters: Optional metadata filters (e.g. language).
            use_reranker: Whether to apply the cross-encoder reranker stage.

        Returns:
            Ranked list of chunk dictionaries with scores and metadata.
        """
        retrieval_mode = mode or settings.RETRIEVAL_MODE

        # ── 1. Vector Only Mode ───────────────────────────────────────────────
        if retrieval_mode == "vector_only":
            query_vec = self._embedding_service.embed_query(query)
            results = self._vector_store.search(
                repository_id, query_vec, top_k=top_k, filters=filters
            )
            for r in results:
                r["retriever"] = "vector"
            return results

        # ── 2. BM25 Only Mode ─────────────────────────────────────────────────
        if retrieval_mode == "bm25_only":
            results = self._bm25_retriever.search(
                repository_id, query, top_k=top_k, filters=filters
            )
            for r in results:
                r["retriever"] = "bm25"
            return results

        # ── 3. Hybrid Mode (Vector + BM25 -> RRF -> Reranker) ─────────────────
        query_vec = self._embedding_service.embed_query(query)

        # Retrieve candidate pools
        vector_candidates = self._vector_store.search(
            repository_id, query_vec, top_k=candidate_pool_size, filters=filters
        )
        bm25_candidates = self._bm25_retriever.search(
            repository_id, query, top_k=candidate_pool_size, filters=filters
        )

        # If one retriever has no results (e.g. BM25 index not yet built), fallback to the other
        if not vector_candidates and not bm25_candidates:
            return []
        if not bm25_candidates:
            candidates = vector_candidates[:candidate_pool_size]
        elif not vector_candidates:
            candidates = bm25_candidates[:candidate_pool_size]
        else:
            # Fuse with Reciprocal Rank Fusion
            candidates = reciprocal_rank_fusion(
                {"vector": vector_candidates, "bm25": bm25_candidates},
                k=60,
                top_n=candidate_pool_size,
            )

        # Optional Reranker stage
        if use_reranker and candidates:
            return self._reranker_service.rerank(query, candidates, top_k=top_k)

        return candidates[:top_k]

