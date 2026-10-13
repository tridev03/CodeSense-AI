"""
Cross-Encoder Reranker Service.

Implements cross-encoder reranking over retrieved candidate chunks using
BAAI/bge-reranker-base. Scores query-document pairs jointly to capture deep
token interactions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from backend.config.settings import settings

logger = logging.getLogger(__name__)

_reranker_instance: Optional["RerankerService"] = None


def get_reranker_service() -> "RerankerService":
    """Return the singleton RerankerService."""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = RerankerService()
    return _reranker_instance


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


class RerankerService:
    """
    Reranks candidate chunks using a cross-encoder model.

    Default backend: BAAI/bge-reranker-base.
    Includes a deterministic mock fallback for testing and development environments.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self.model_name = model_name or settings.RERANKER_MODEL
        self.device = _resolve_device(device or settings.RERANKER_DEVICE)
        self._model = None
        self._is_mock = settings.is_testing

    def _load_model(self) -> None:
        """Lazy-load the cross-encoder model."""
        if self._model is not None or self._is_mock:
            return

        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading reranker model: %s on %s", self.model_name, self.device)
            self._model = CrossEncoder(self.model_name, device=self.device)
            logger.info("Reranker model loaded successfully")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Using mock reranker. "
                "Install with: pip install sentence-transformers"
            )
            self._is_mock = True
        except Exception as exc:
            logger.warning(
                "Failed to load reranker model '%s': %s. Using mock reranker.",
                self.model_name, exc
            )
            self._is_mock = True

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Score and reorder candidate chunks with the cross-encoder.

        Args:
            query: The user search query or question.
            candidates: List of candidate chunk dicts [{'id': ..., 'content': ..., 'metadata': ...}].
            top_k: Number of highest-scoring chunks to return.

        Returns:
            Reordered list of top-k candidates with 'rerank_score' attached.
        """
        if not candidates:
            return []

        self._load_model()

        if self._is_mock or self._model is None:
            return self._mock_rerank(query, candidates, top_k)

        pairs = [[query, c.get("content", "")] for c in candidates]

        try:
            scores = self._model.predict(pairs)
            if hasattr(scores, "tolist"):
                scores = scores.tolist()

            reranked = []
            for candidate, score in zip(candidates, scores):
                item = dict(candidate)
                item["rerank_score"] = float(score)
                reranked.append(item)

            reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
            return reranked[:top_k]

        except Exception as exc:
            logger.error("Reranking failed: %s. Falling back to original candidate order.", exc)
            return candidates[:top_k]

    def _mock_rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Deterministic mock reranker for testing.

        Boosts candidates containing exact query terms, otherwise maintains score order.
        """
        query_words = set(query.lower().split())
        reranked = []

        for c in candidates:
            item = dict(c)
            content_lower = item.get("content", "").lower()
            overlap = sum(1 for w in query_words if w in content_lower)

            base_score = float(item.get("score", 0.5))
            # Boost score based on query term overlap
            mock_score = base_score + (overlap * 0.2)
            item["rerank_score"] = round(mock_score, 4)
            reranked.append(item)

        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]
