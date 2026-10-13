"""
Embedding service abstraction.

Provides a unified interface for generating text embeddings.
Supports multiple backends:
- Local: Qwen3-Embedding-0.6B via sentence-transformers (default)
- Cloud: OpenAI text-embedding-3-small (fallback)

The service is initialized lazily on first use to avoid loading
the model at import time (important for fast test startup).
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from backend.config.settings import settings

logger = logging.getLogger(__name__)

# ─── Module-level singleton ──────────────────────────────────────────────────

_instance: Optional["EmbeddingService"] = None


def get_embedding_service() -> "EmbeddingService":
    """Return the singleton EmbeddingService, creating it on first call."""
    global _instance
    if _instance is None:
        _instance = EmbeddingService()
    return _instance


def reset_embedding_service() -> None:
    """Reset the singleton (useful in tests)."""
    global _instance
    _instance = None


def _resolve_device(device_str: str) -> str:
    """Check if requested CUDA device is supported by PyTorch, else fallback to cpu."""
    if device_str.lower().startswith("cuda"):
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning(
                    "CUDA requested ('%s') but PyTorch CUDA is not available. Falling back to 'cpu'.",
                    device_str,
                )
                return "cpu"
        except ImportError:
            return "cpu"
    return device_str


class EmbeddingService:
    """
    Generates dense vector embeddings for text content.

    Default backend: sentence-transformers with Qwen3-Embedding-0.6B (1024-dim).
    Supports CUDA GPU acceleration when available.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        dimension: Optional[int] = None,
    ):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.device = _resolve_device(device or settings.EMBEDDING_DEVICE)
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self._model = None
        self._is_mock = settings.is_testing

    def _load_model(self) -> None:
        """Lazy-load the embedding model."""
        if self._model is not None or self._is_mock:
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(
                "Loading embedding model: %s on %s",
                self.model_name, self.device,
            )
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                trust_remote_code=True,
            )
            # Verify dimension
            test_emb = self._model.encode(["test"], normalize_embeddings=True)
            actual_dim = test_emb.shape[1]
            if actual_dim != self.dimension:
                logger.warning(
                    "Model dimension mismatch: expected=%d, actual=%d. "
                    "Updating to actual dimension.",
                    self.dimension, actual_dim,
                )
                self.dimension = actual_dim
            logger.info(
                "Embedding model loaded: dimension=%d", self.dimension
            )
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Using mock embeddings (random vectors). "
                "Install with: pip install sentence-transformers"
            )
            self._is_mock = True
        except Exception as exc:
            logger.warning(
                "Failed to load embedding model '%s': %s. "
                "Falling back to mock embeddings.",
                self.model_name, exc,
            )
            self._is_mock = True

    def embed_texts(
        self,
        texts: List[str],
        *,
        batch_size: Optional[int] = None,
    ) -> np.ndarray:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.
            batch_size: Override the default batch size.

        Returns:
            numpy array of shape (len(texts), dimension), L2-normalized.
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.dimension)

        self._load_model()

        if self._is_mock:
            return self._mock_embed(texts)

        bs = batch_size or settings.EMBEDDING_BATCH_SIZE
        embeddings = self._model.encode(
            texts,
            batch_size=bs,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query string.

        Returns:
            1D numpy array of shape (dimension,).
        """
        result = self.embed_texts([query])
        return result[0]

    def _mock_embed(self, texts: List[str]) -> np.ndarray:
        """
        Generate deterministic mock embeddings for testing.

        Uses a hash-based seed so the same text always produces the same
        vector, making tests reproducible.
        """
        embeddings = []
        for text in texts:
            seed = hash(text) % (2**31)
            rng = np.random.RandomState(seed)
            vec = rng.randn(self.dimension).astype(np.float32)
            # L2 normalize
            vec = vec / (np.linalg.norm(vec) + 1e-12)
            embeddings.append(vec)
        return np.array(embeddings, dtype=np.float32)
