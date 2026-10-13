"""
Pydantic schemas for search, chat (RAG), and retrieval evaluation operations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Payload for code and documentation semantic search."""
    query: str = Field(..., min_length=1, description="Natural language or code query")
    top_k: int = Field(default=10, ge=1, le=100, description="Max results to return")
    language: Optional[str] = Field(None, description="Filter by programming language")
    content_type: Optional[str] = Field(None, description="Filter by content type (code, documentation, configuration)")
    file_path: Optional[str] = Field(None, description="Filter by file path substring")
    retrieval_mode: Optional[str] = Field(default="hybrid", description="vector_only | bm25_only | hybrid")
    use_reranker: Optional[bool] = Field(default=True, description="Whether to apply BGE cross-encoder reranking")


class SearchResultItem(BaseModel):
    """A single retrieved chunk match with metadata."""
    chunk_id: str
    file_path: str
    content_type: str
    content: str
    score: float
    language: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    symbol_type: Optional[str] = None
    class_name: Optional[str] = None
    function_name: Optional[str] = None
    context_header: Optional[str] = None
    section_title: Optional[str] = None
    rerank_score: Optional[float] = None
    retriever: Optional[str] = None


class SearchResponse(BaseModel):
    """Response returned by the semantic search endpoint."""
    query: str
    repository_id: str
    retrieval_mode: str
    total_results: int
    results: List[SearchResultItem]


class Citation(BaseModel):
    """Specific code or documentation citation supporting an LLM answer."""
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    symbol: Optional[str] = None
    snippet: Optional[str] = None


class ChatRequest(BaseModel):
    """Payload for asking a question about a repository."""
    query: str = Field(..., min_length=1, description="Developer question about the repository")
    top_k: int = Field(default=10, ge=1, le=50, description="Context chunks to retrieve")
    include_citations: bool = Field(default=True, description="Whether to include structured citations")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata filters")
    retrieval_mode: Optional[str] = Field(default="hybrid", description="vector_only | bm25_only | hybrid")
    use_reranker: Optional[bool] = Field(default=True, description="Whether to apply BGE cross-encoder reranking")


class ChatResponse(BaseModel):
    """Grounded answer from the LLM with evidence citations."""
    query: str
    answer: str
    repository_id: str
    retrieval_mode: str
    citations: List[Citation] = Field(default_factory=list)
    model: str
    tokens_used: Optional[int] = None


class ChatStreamChunk(BaseModel):
    """A single SSE chunk emitted during a streaming chat response."""
    token: Optional[str] = None
    citations: Optional[List[Citation]] = None
    done: bool = False
    error: Optional[str] = None


# ─── Retrieval Evaluation & Ablation Schemas ──────────────────────────────────


class AblationQueryItem(BaseModel):
    """Single test query item with expected relevant chunks or file names."""
    query: str
    expected_chunk_ids: Optional[List[str]] = Field(default_factory=list)
    expected_files: Optional[List[str]] = Field(default_factory=list)


class AblationRequest(BaseModel):
    """Request payload to run retrieval ablation benchmark on a repository."""
    k: int = Field(default=5, ge=1, le=50, description="Rank threshold K for metrics (Recall@K, etc.)")
    queries: List[AblationQueryItem] = Field(..., min_length=1, description="Evaluation queries with ground truth")
