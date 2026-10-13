"""
BM25 Keyword Retriever for code and documentation.

Provides lexical search across repository chunks using BM25Okapi and code-aware
tokenization. Maintained independently from vector retrieval for hybrid search.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

from backend.ingestion.models import CodeChunk
from backend.retrieval.tokenizer import tokenize_code

logger = logging.getLogger(__name__)


class BM25Index:
    """
    In-memory BM25 index for a single repository.
    """

    def __init__(self, chunks: List[CodeChunk]):
        self.chunks = chunks
        # Tokenize all chunk texts
        self.corpus = [
            tokenize_code(
                f"{c.file_path} {c.function_name or ''} {c.class_name or ''} {c.section_title or ''} {c.content}"
            )
            for c in chunks
        ]
        # Prevent division by zero if all docs are empty
        if not any(self.corpus):
            self.corpus = [["empty"] for _ in chunks]

        self.bm25 = BM25Okapi(self.corpus)

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Score all chunks against the query and return top-k matches.
        """
        if not self.chunks:
            return []

        tokenized_query = tokenize_code(query)
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)

        query_set = set(tokenized_query)

        # Pair chunks with scores
        scored_results = []
        for i, score in enumerate(scores):
            doc_tokens = set(self.corpus[i])
            overlap = query_set.intersection(doc_tokens)
            if not overlap:
                continue

            chunk = self.chunks[i]
            payload = chunk.to_metadata_dict()

            # Apply metadata filters if provided
            if filters:
                match = all(payload.get(k) == v for k, v in filters.items())
                if not match:
                    continue

            # In small test corpora, BM25Okapi IDF can be 0 or negative for common terms.
            # We ensure matching documents receive a valid positive score.
            final_score = float(score) if score > 0.0 else float(len(overlap))

            scored_results.append(
                {
                    "id": chunk.chunk_id,
                    "score": final_score,
                    "content": chunk.content,
                    "metadata": payload,
                }
            )

        # Sort descending by BM25 score
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:top_k]


import pickle
from pathlib import Path
from backend.config.settings import settings

# Registry of BM25 indexes by repository UUID
_bm25_indices: Dict[str, BM25Index] = {}


def get_default_bm25_storage_dir() -> Path:
    """Return directory for persistent BM25 indexes (REL-04)."""
    base = Path(settings.REPOS_STORAGE_PATH)
    storage_dir = base.parent / "bm25"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


class BM25Retriever:
    """
    Manages repository-isolated BM25 indexes with in-memory caching
    and durable disk persistence (REL-04).
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self._indices = _bm25_indices
        self._storage_dir = storage_dir or get_default_bm25_storage_dir()

    def _get_index_file_path(self, repository_id: str) -> Path:
        return self._storage_dir / f"{repository_id}.pkl"

    def build_index(self, repository_id: str, chunks: List[CodeChunk]) -> int:
        """
        Build, register, and persist a BM25 index for a repository.
        """
        if not chunks:
            return 0

        index = BM25Index(chunks)
        repo_key = str(repository_id)
        self._indices[repo_key] = index

        # Persist to disk (REL-04)
        try:
            target_path = self._get_index_file_path(repo_key)
            with open(target_path, "wb") as f:
                pickle.dump(index, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.info("Persisted BM25 index to %s", target_path)
        except Exception as exc:
            logger.warning("Failed to persist BM25 index for %s to disk: %s", repository_id, exc)

        logger.info(
            "Built BM25 index for repository %s with %d chunks",
            repository_id, len(chunks)
        )
        return len(chunks)

    def load_from_disk(self, repository_id: str) -> Optional[BM25Index]:
        """
        Load a persisted BM25 index from disk into memory cache.
        """
        repo_key = str(repository_id)
        target_path = self._get_index_file_path(repo_key)
        if not target_path.exists():
            return None

        try:
            with open(target_path, "rb") as f:
                index: BM25Index = pickle.load(f)
            self._indices[repo_key] = index
            logger.info("Loaded BM25 index from disk for %s (%d chunks)", repository_id, len(index.chunks))
            return index
        except Exception as exc:
            logger.error("Failed to load BM25 index from disk for %s: %s", repository_id, exc)
            return None

    def search(
        self,
        repository_id: str,
        query: str,
        *,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search the repository's BM25 index (in-memory or loaded from disk).
        """
        repo_key = str(repository_id)
        index = self._indices.get(repo_key)
        if not index:
            # Attempt to auto-load from disk (REL-04)
            index = self.load_from_disk(repo_key)

        if not index:
            logger.warning("No BM25 index found for repository %s", repository_id)
            return []

        return index.search(query, top_k=top_k, filters=filters)

    def delete_index(self, repository_id: str) -> None:
        """Remove a repository's BM25 index from memory and disk."""
        repo_key = str(repository_id)
        self._indices.pop(repo_key, None)
        target_path = self._get_index_file_path(repo_key)
        if target_path.exists():
            try:
                target_path.unlink()
                logger.info("Deleted persisted BM25 index file %s", target_path)
            except Exception as exc:
                logger.warning("Failed to delete BM25 file %s: %s", target_path, exc)
        logger.info("Deleted BM25 index for repository %s", repository_id)

    def has_index(self, repository_id: str) -> bool:
        """Check if an index exists in memory or on disk."""
        repo_key = str(repository_id)
        if repo_key in self._indices:
            return True
        return self._get_index_file_path(repo_key).exists()


