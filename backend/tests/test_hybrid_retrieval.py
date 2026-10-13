"""
Unit tests for HybridRetriever.

Tests:
- vector_only retrieval mode
- bm25_only retrieval mode
- hybrid retrieval mode (RRF + Reranker)
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.ingestion.models import CodeChunk, ContentType
from backend.retrieval import VectorStoreService
from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.hybrid import HybridRetriever


@pytest.fixture
def hybrid_setup():
    """Set up VectorStore and BM25 index with sample chunks."""
    vector_store = VectorStoreService(dimension=1024)
    bm25 = BM25Retriever()
    repo_id = "test-hybrid-repo"

    chunks = [
        CodeChunk(
            chunk_id="chunk-auth",
            repository_id=repo_id,
            file_path="src/auth.py",
            language="python",
            content="def authenticate_user(): pass",
        ),
        CodeChunk(
            chunk_id="chunk-db",
            repository_id=repo_id,
            file_path="src/db.py",
            language="python",
            content="def connect_postgres(): pass",
        ),
    ]

    # Index into vector store
    vecs = np.random.randn(2, 1024).astype(np.float32)
    vector_store.upsert_chunks(repo_id, chunks, vecs)

    # Index into BM25
    bm25.build_index(repo_id, chunks)

    retriever = HybridRetriever(
        vector_store=vector_store,
        bm25_retriever=bm25,
    )
    return retriever, repo_id


def test_retriever_modes(hybrid_setup) -> None:
    """Verify vector_only, bm25_only, and hybrid modes execute and return results."""
    retriever, repo_id = hybrid_setup

    # 1. Vector only
    vec_results = retriever.retrieve(repo_id, "authenticate", mode="vector_only", top_k=2)
    assert len(vec_results) > 0
    assert vec_results[0]["retriever"] == "vector"

    # 2. BM25 only
    bm25_results = retriever.retrieve(repo_id, "authenticate", mode="bm25_only", top_k=2)
    assert len(bm25_results) > 0
    assert bm25_results[0]["id"] == "chunk-auth"
    assert bm25_results[0]["retriever"] == "bm25"

    # 3. Hybrid mode (RRF + Reranker)
    hybrid_results = retriever.retrieve(repo_id, "authenticate", mode="hybrid", top_k=2)
    assert len(hybrid_results) > 0
    assert "rerank_score" in hybrid_results[0]
