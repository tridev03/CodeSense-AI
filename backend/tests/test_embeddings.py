"""
Unit tests for the Embedding Service.

Tests:
- Single query embedding
- Batch text embedding
- Output dimensions and normalization
- Deterministic mock embeddings
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.embeddings import EmbeddingService


def test_embedding_service_dimensions_and_norm() -> None:
    """Verify embeddings have expected dimension and unit length."""
    service = EmbeddingService(dimension=1024)

    vec = service.embed_query("How does authentication work?")
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (1024,)

    # Verify unit normalization (L2 norm ≈ 1.0)
    norm = np.linalg.norm(vec)
    assert pytest.approx(norm, 1e-4) == 1.0


def test_embedding_service_batch() -> None:
    """Verify batch embedding produces correct array shape."""
    service = EmbeddingService(dimension=1024)

    texts = [
        "def authenticate(user, password): pass",
        "class UserRepository: pass",
        "DATABASE_URL=postgresql://localhost:5432",
    ]
    vecs = service.embed_texts(texts)
    assert isinstance(vecs, np.ndarray)
    assert vecs.shape == (3, 1024)

    # Empty batch
    empty_vecs = service.embed_texts([])
    assert empty_vecs.shape == (0, 1024)


def test_embedding_service_deterministic() -> None:
    """Verify same text produces identical embedding in mock mode."""
    service = EmbeddingService(dimension=1024)

    vec1 = service.embed_query("import os")
    vec2 = service.embed_query("import os")
    vec3 = service.embed_query("import sys")

    assert np.allclose(vec1, vec2)
    assert not np.allclose(vec1, vec3)

