"""
Qdrant vector store service.

Manages:
- Collection lifecycle (create, delete, check)
- Batch vector insertion with metadata payloads
- Similarity search with optional metadata filtering
- Repository-scoped collection isolation

Each repository gets its own Qdrant collection:
  collection name = "repo_{repository_id}"

This isolates embeddings per repository and allows easy deletion
when a repository is removed.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

from backend.config.settings import settings
from backend.ingestion.models import CodeChunk

logger = logging.getLogger(__name__)


# Shared in-memory mock store across instances for testing/offline mode
_shared_mock_store: Dict[str, List[Dict[str, Any]]] = {}


def _collection_name(repository_id: str) -> str:
    """Generate a deterministic Qdrant collection name for a repository."""
    # Clean up UUID format for collection naming
    clean_id = str(repository_id).replace("-", "")
    return f"repo_{clean_id}"


class VectorStoreService:
    """
    Manages Qdrant vector database operations.

    Lazily initializes the Qdrant client on first use.
    Falls back to an in-memory mock store when Qdrant is unavailable
    (for tests and development without Docker).
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        dimension: Optional[int] = None,
    ):
        self._url = url or settings.QDRANT_URL
        self._api_key = api_key or settings.QDRANT_API_KEY
        self._dimension = dimension or settings.EMBEDDING_DIMENSION
        self._client = None
        self._is_mock = settings.is_testing
        self._mock_store = _shared_mock_store

    def _get_client(self):
        """Lazy-initialize the Qdrant client."""
        if self._client is not None:
            return self._client

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams

            self._client = QdrantClient(
                url=self._url,
                api_key=self._api_key,
                timeout=30,
            )
            # Verify connection
            self._client.get_collections()
            logger.info("Connected to Qdrant at %s", self._url)
            return self._client

        except ImportError:
            logger.warning(
                "qdrant-client not installed. Using in-memory mock store. "
                "Install with: pip install qdrant-client"
            )
            self._is_mock = True
            return None
        except Exception as exc:
            logger.warning(
                "Failed to connect to Qdrant at %s: %s. "
                "Using in-memory mock store.",
                self._url, exc,
            )
            self._is_mock = True
            return None

    def ensure_collection(self, repository_id: str) -> str:
        """
        Create a Qdrant collection for a repository if it doesn't exist.

        Returns the collection name.
        """
        col_name = _collection_name(repository_id)

        if self._is_mock or self._get_client() is None:
            self._mock_store.setdefault(col_name, [])
            logger.info("Mock collection created: %s", col_name)
            return col_name

        from qdrant_client.http.models import Distance, VectorParams

        collections = [c.name for c in self._client.get_collections().collections]
        if col_name not in collections:
            self._client.create_collection(
                collection_name=col_name,
                vectors_config=VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection: %s (dim=%d)",
                col_name, self._dimension,
            )
        else:
            logger.info("Collection already exists: %s", col_name)

        return col_name

    def delete_collection(self, repository_id: str) -> None:
        """Delete a repository's vector collection."""
        col_name = _collection_name(repository_id)

        if self._is_mock:
            self._mock_store.pop(col_name, None)
            return

        client = self._get_client()
        if client:
            try:
                client.delete_collection(col_name)
                logger.info("Deleted collection: %s", col_name)
            except Exception as exc:
                logger.warning("Failed to delete collection %s: %s", col_name, exc)

    def upsert_chunks(
        self,
        repository_id: str,
        chunks: List[CodeChunk],
        embeddings: np.ndarray,
    ) -> int:
        """
        Insert or update chunk vectors with metadata payloads.

        Args:
            repository_id: Repository UUID string.
            chunks: List of CodeChunk objects.
            embeddings: numpy array of shape (len(chunks), dimension).

        Returns:
            Number of vectors upserted.
        """
        if len(chunks) == 0:
            return 0

        col_name = self.ensure_collection(repository_id)

        if self._is_mock:
            for chunk, vector in zip(chunks, embeddings):
                self._mock_store[col_name].append({
                    "id": chunk.chunk_id,
                    "vector": vector.tolist(),
                    "payload": chunk.to_metadata_dict(),
                    "content": chunk.content,
                })
            logger.info(
                "Mock upserted %d vectors into %s", len(chunks), col_name
            )
            return len(chunks)

        from qdrant_client.http.models import PointStruct

        # Batch upsert in groups of 100
        batch_size = 100
        total = 0

        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_vectors = embeddings[i:i + batch_size]

            points = []
            for chunk, vector in zip(batch_chunks, batch_vectors):
                payload = chunk.to_metadata_dict()
                payload["content"] = chunk.content  # Store content for retrieval
                points.append(PointStruct(
                    id=chunk.chunk_id,
                    vector=vector.tolist(),
                    payload=payload,
                ))

            self._client.upsert(
                collection_name=col_name,
                points=points,
            )
            total += len(points)

        logger.info("Upserted %d vectors into %s", total, col_name)
        return total

    def search(
        self,
        repository_id: str,
        query_vector: np.ndarray,
        *,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search in a repository's collection.

        Args:
            repository_id: Repository UUID string.
            query_vector: 1D numpy array (dimension,).
            top_k: Number of results to return.
            filters: Optional metadata filters (e.g. {"language": "python"}).

        Returns:
            List of dicts with keys: id, score, content, metadata.
        """
        col_name = _collection_name(repository_id)

        if self._is_mock:
            return self._mock_search(col_name, query_vector, top_k, filters)

        client = self._get_client()
        if client is None:
            return []

        # Build Qdrant filter
        qdrant_filter = None
        if filters:
            from qdrant_client.http.models import FieldCondition, Filter, MatchValue
            conditions = []
            for key, value in filters.items():
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )
            qdrant_filter = Filter(must=conditions)

        # Gracefully handle collection not existing yet (e.g. unindexed repo)
        try:
            if hasattr(client, "collection_exists") and not client.collection_exists(col_name):
                return []
        except Exception:
            pass

        try:
            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name=col_name,
                    query=query_vector.tolist(),
                    limit=top_k,
                    query_filter=qdrant_filter,
                    with_payload=True,
                )
                results = response.points
            else:
                results = client.search(
                    collection_name=col_name,
                    query_vector=query_vector.tolist(),
                    limit=top_k,
                    query_filter=qdrant_filter,
                    with_payload=True,
                )
        except Exception as exc:
            logger.warning("Qdrant search failed for collection %s: %s", col_name, exc)
            return []

        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                "content": (hit.payload or {}).get("content", ""),
                "metadata": {
                    k: v for k, v in (hit.payload or {}).items() if k != "content"
                },
            }
            for hit in results
        ]

    def _mock_search(
        self,
        collection_name: str,
        query_vector: np.ndarray,
        top_k: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """In-memory cosine similarity search for testing."""
        points = self._mock_store.get(collection_name, [])
        if not points:
            return []

        # Apply filters
        if filters:
            filtered = []
            for p in points:
                payload = p["payload"]
                match = all(payload.get(k) == v for k, v in filters.items())
                if match:
                    filtered.append(p)
            points = filtered

        if not points:
            return []

        # Compute cosine similarity
        query_norm = query_vector / (np.linalg.norm(query_vector) + 1e-12)
        scored = []
        for p in points:
            vec = np.array(p["vector"], dtype=np.float32)
            vec_norm = vec / (np.linalg.norm(vec) + 1e-12)
            score = float(np.dot(query_norm, vec_norm))
            scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        return [
            {
                "id": p["id"],
                "score": score,
                "content": p.get("content", ""),
                "metadata": {
                    k: v for k, v in p["payload"].items() if k != "content"
                },
            }
            for score, p in top
        ]

    def get_collection_count(self, repository_id: str) -> int:
        """Return the number of vectors in a collection."""
        col_name = _collection_name(repository_id)

        if self._is_mock:
            return len(self._mock_store.get(col_name, []))

        client = self._get_client()
        if client is None:
            return 0

        try:
            info = client.get_collection(col_name)
            return info.points_count or 0
        except Exception:
            return 0
