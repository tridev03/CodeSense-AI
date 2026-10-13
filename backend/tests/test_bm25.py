"""
Unit tests for BM25 keyword retriever.

Tests:
- Index creation and persistence per repository
- Exact symbol and identifier matching
- Metadata filtering
- Index deletion
"""
from __future__ import annotations

import pytest

from backend.ingestion.models import CodeChunk, ContentType, SymbolType
from backend.retrieval.bm25 import BM25Retriever


def test_bm25_exact_symbol_match() -> None:
    """Verify BM25 finds exact function and class identifiers."""
    retriever = BM25Retriever()
    repo_id = "test-bm25-repo-1"

    chunk1 = CodeChunk(
        chunk_id="chunk-auth-1",
        repository_id=repo_id,
        file_path="src/auth.py",
        language="python",
        content_type=ContentType.CODE,
        symbol_type=SymbolType.FUNCTION,
        function_name="verify_jwt_token",
        content="def verify_jwt_token(token: str) -> bool: return True",
    )
    chunk2 = CodeChunk(
        chunk_id="chunk-db-1",
        repository_id=repo_id,
        file_path="src/db.py",
        language="python",
        content_type=ContentType.CODE,
        symbol_type=SymbolType.FUNCTION,
        function_name="connect_database",
        content="def connect_database(): return True",
    )

    retriever.build_index(repo_id, [chunk1, chunk2])

    # Search for specific identifier
    results = retriever.search(repo_id, "verify_jwt_token", top_k=5)
    assert len(results) > 0
    assert results[0]["id"] == "chunk-auth-1"
    assert results[0]["metadata"]["function_name"] == "verify_jwt_token"


def test_bm25_metadata_filtering() -> None:
    """Verify BM25 search respects language and path filters."""
    retriever = BM25Retriever()
    repo_id = "test-bm25-filters"

    chunk_py = CodeChunk(
        chunk_id="py-chunk",
        repository_id=repo_id,
        file_path="service.py",
        language="python",
        content="class DataService: pass",
    )
    chunk_ts = CodeChunk(
        chunk_id="ts-chunk",
        repository_id=repo_id,
        file_path="service.ts",
        language="typescript",
        content="export class DataService {}",
    )

    retriever.build_index(repo_id, [chunk_py, chunk_ts])

    # Filter for typescript
    ts_results = retriever.search(repo_id, "DataService", filters={"language": "typescript"})
    assert len(ts_results) == 1
    assert ts_results[0]["id"] == "ts-chunk"


def test_bm25_index_lifecycle() -> None:
    """Verify BM25 index deletion."""
    retriever = BM25Retriever()
    repo_id = "test-bm25-del"

    chunk = CodeChunk(
        chunk_id="chunk-1",
        repository_id=repo_id,
        file_path="test.py",
        content="print('hello')",
    )
    retriever.build_index(repo_id, [chunk])
    assert retriever.has_index(repo_id)

    retriever.delete_index(repo_id)
    assert not retriever.has_index(repo_id)
    assert retriever.search(repo_id, "hello") == []

