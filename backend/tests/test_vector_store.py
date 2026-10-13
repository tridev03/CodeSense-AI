"""
Unit tests for Qdrant VectorStoreService.

Tests:
- Collection creation & isolation per repository
- Chunk vector upsert with metadata payload
- Similarity search & top-k ranking
- Metadata filtering (by language, symbol type, etc.)
- Collection deletion & cleanup
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.ingestion.models import CodeChunk, ContentType, SymbolType
from backend.retrieval import VectorStoreService


def test_vector_store_upsert_and_search() -> None:
    """Verify upserting chunks and performing similarity search."""
    store = VectorStoreService(dimension=128)
    repo_id = "test-repo-1"

    # Create test chunks
    chunk1 = CodeChunk(
        chunk_id="chunk-1",
        repository_id=repo_id,
        file_path="src/auth.py",
        language="python",
        content_type=ContentType.CODE,
        content="def authenticate_user(username, password): pass",
        symbol_type=SymbolType.FUNCTION,
        function_name="authenticate_user",
        start_line=10,
        end_line=20,
    )
    chunk2 = CodeChunk(
        chunk_id="chunk-2",
        repository_id=repo_id,
        file_path="docs/README.md",
        content_type=ContentType.DOCUMENTATION,
        content="# Documentation for authentication",
        section_title="Authentication",
        start_line=1,
        end_line=5,
    )

    # Make distinctive vectors
    vec1 = np.zeros(128, dtype=np.float32)
    vec1[0] = 1.0  # Strongly aligns with query_vec
    vec2 = np.zeros(128, dtype=np.float32)
    vec2[1] = 1.0

    embeddings = np.stack([vec1, vec2])
    count = store.upsert_chunks(repo_id, [chunk1, chunk2], embeddings)
    assert count == 2

    # Query vector close to vec1
    query_vec = np.zeros(128, dtype=np.float32)
    query_vec[0] = 1.0

    results = store.search(repo_id, query_vec, top_k=2)
    assert len(results) == 2
    assert results[0]["id"] == "chunk-1"
    assert results[0]["score"] > results[1]["score"]
    assert results[0]["metadata"]["function_name"] == "authenticate_user"


def test_vector_store_metadata_filtering() -> None:
    """Verify search respects metadata filters."""
    store = VectorStoreService(dimension=64)
    repo_id = "test-repo-filters"

    chunk_py = CodeChunk(
        chunk_id="py-chunk",
        repository_id=repo_id,
        file_path="app.py",
        language="python",
        content_type=ContentType.CODE,
        content="print('python')",
    )
    chunk_ts = CodeChunk(
        chunk_id="ts-chunk",
        repository_id=repo_id,
        file_path="app.ts",
        language="typescript",
        content_type=ContentType.CODE,
        content="console.log('typescript')",
    )

    embeddings = np.random.randn(2, 64).astype(np.float32)
    store.upsert_chunks(repo_id, [chunk_py, chunk_ts], embeddings)

    query_vec = np.random.randn(64).astype(np.float32)

    # Filter for python only
    py_results = store.search(repo_id, query_vec, top_k=5, filters={"language": "python"})
    assert len(py_results) == 1
    assert py_results[0]["id"] == "py-chunk"

    # Filter for typescript only
    ts_results = store.search(repo_id, query_vec, top_k=5, filters={"language": "typescript"})
    assert len(ts_results) == 1
    assert ts_results[0]["id"] == "ts-chunk"


def test_vector_store_collection_delete() -> None:
    """Verify deleting a collection removes all indexed points."""
    store = VectorStoreService(dimension=32)
    repo_id = "test-repo-delete"

    chunk = CodeChunk(
        chunk_id="chunk-to-delete",
        repository_id=repo_id,
        file_path="test.py",
        content="temp code",
    )
    vec = np.ones((1, 32), dtype=np.float32)
    store.upsert_chunks(repo_id, [chunk], vec)

    assert store.get_collection_count(repo_id) == 1
    store.delete_collection(repo_id)
    assert store.get_collection_count(repo_id) == 0

