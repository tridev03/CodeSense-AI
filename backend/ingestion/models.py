"""
Pydantic data models for the ingestion pipeline.

These models flow through the pipeline stages:
  Scanner → Parser → Chunker → (Phase 3) Embedder

They are NOT ORM models. They are lightweight, immutable, and serializable
data containers used within a single ingestion run.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ─── Enumerations ─────────────────────────────────────────────────────────────


class ContentType(str, Enum):
    """Classification of a discovered file."""
    CODE = "code"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    GIT_HISTORY = "git_history"
    UNKNOWN = "unknown"


class SymbolType(str, Enum):
    """Kind of code symbol extracted by an AST parser."""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    IMPORT = "import"
    BLOCK = "block"              # Catch-all for structural blocks


# ─── Scanner Output ───────────────────────────────────────────────────────────


class DiscoveredFile(BaseModel):
    """A file found by the scanner, classified and ready for parsing."""
    path: str = Field(..., description="Path relative to the repository root")
    absolute_path: str = Field(..., description="Absolute filesystem path")
    content_type: ContentType
    language: Optional[str] = Field(
        None, description="Programming language (python, javascript, typescript, etc.)"
    )
    size_bytes: int = 0
    encoding: str = "utf-8"


# ─── Parser Output ────────────────────────────────────────────────────────────


class CodeSymbol(BaseModel):
    """A single symbol extracted from source code by an AST parser."""
    name: str = Field(..., description="Symbol name (function name, class name, etc.)")
    symbol_type: SymbolType
    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    source_code: str = Field(..., description="Full source code of the symbol")
    parent_class: Optional[str] = Field(
        None, description="Enclosing class name, if this is a method"
    )
    docstring: Optional[str] = None
    decorators: List[str] = Field(default_factory=list)
    parameters: Optional[str] = Field(
        None, description="Parameter signature string, e.g. '(self, x: int, y: int)'"
    )


class ParsedFile(BaseModel):
    """Result of parsing a single file — symbols + raw content."""
    file_path: str = Field(..., description="Relative path within the repository")
    language: Optional[str] = None
    content_type: ContentType
    raw_content: str = Field(..., description="Full file contents as a string")
    symbols: List[CodeSymbol] = Field(
        default_factory=list,
        description="Extracted code symbols (empty for docs/config files)",
    )
    total_lines: int = 0


# ─── Chunker Output ──────────────────────────────────────────────────────────


import hashlib


def generate_deterministic_chunk_id(
    repository_id: Optional[str],
    file_path: str,
    content: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """
    Generate a deterministic UUIDv5 chunk identifier (REL-02).
    
    Guarantees that re-ingesting identical content yields identical chunk IDs,
    making vector store and database upserts completely idempotent.
    """
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    key = f"{repository_id or 'repo'}:{file_path}:{start_line or 0}:{end_line or 0}:{content_hash}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


class CodeChunk(BaseModel):
    """
    A single chunk ready for embedding.

    This is the atomic unit that gets stored in the vector database.
    Every chunk carries enough metadata to generate precise citations.
    """
    chunk_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this chunk",
    )
    repository_id: Optional[str] = None

    def ensure_deterministic_id(self, repository_id: Optional[str] = None) -> str:
        """Enforce deterministic chunk_id based on content and position (REL-02)."""
        repo_id = repository_id or self.repository_id
        self.chunk_id = generate_deterministic_chunk_id(
            repo_id,
            self.file_path,
            self.content,
            self.start_line,
            self.end_line,
        )
        if repo_id:
            self.repository_id = repo_id
        return self.chunk_id
    file_path: str
    language: Optional[str] = None
    content_type: ContentType = ContentType.CODE
    content: str = Field(..., description="The text content of this chunk")

    # ── Code-specific metadata ─────────────────────────────────────────────
    symbol_type: Optional[SymbolType] = None
    class_name: Optional[str] = None
    function_name: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    context_header: Optional[str] = Field(
        None,
        description=(
            "Parent context prepended to chunk content so the LLM understands "
            "where this code lives. E.g. 'class AuthService:' for a method chunk."
        ),
    )

    # ── Documentation-specific metadata ────────────────────────────────────
    section_title: Optional[str] = Field(
        None, description="Markdown section heading this chunk belongs to"
    )

    # ── Git-specific metadata ──────────────────────────────────────────────
    commit_hash: Optional[str] = None
    commit_author: Optional[str] = None
    commit_date: Optional[str] = None

    def to_metadata_dict(self) -> dict:
        """
        Return a flat dictionary suitable for Qdrant/vector-DB payload storage.

        None values are excluded to keep payloads compact.
        """
        d = {
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "content_type": self.content_type.value,
        }
        for key in (
            "repository_id", "language", "symbol_type", "class_name",
            "function_name", "start_line", "end_line", "context_header",
            "section_title", "commit_hash", "commit_author", "commit_date",
        ):
            val = getattr(self, key)
            if val is not None:
                d[key] = val.value if isinstance(val, Enum) else val
        return d


class GitCommitInfo(BaseModel):
    """Structured information extracted from a Git commit."""
    hash: str
    short_hash: str
    author_name: str
    author_email: str
    date: str
    message: str
    changed_files: List[str] = Field(default_factory=list)
    diff_summary: Optional[str] = None

