"""
Unit tests for code, documentation, and configuration chunkers.

Tests:
- Code chunker: AST symbol-aligned chunking, context headers, metadata extraction
- Markdown chunker: header hierarchy, section metadata, preamble handling
- Config chunker: JSON/YAML/TOML chunking
- Chunk metadata dictionary generation for Qdrant/vector store
"""
from __future__ import annotations

import pytest

from backend.ingestion.chunkers.code_chunker import chunk_code_file
from backend.ingestion.chunkers.doc_chunker import chunk_configuration, chunk_markdown
from backend.ingestion.models import (
    CodeChunk,
    CodeSymbol,
    ContentType,
    ParsedFile,
    SymbolType,
)


def test_code_chunker_symbol_metadata() -> None:
    """Test that code chunks carry rich metadata and context headers."""
    raw_code = '''class AuthService:
    def authenticate(self, username: str) -> bool:
        return True
'''
    symbols = [
        CodeSymbol(
            name="AuthService",
            symbol_type=SymbolType.CLASS,
            start_line=1,
            end_line=3,
            source_code=raw_code,
        ),
        CodeSymbol(
            name="authenticate",
            symbol_type=SymbolType.METHOD,
            start_line=2,
            end_line=3,
            source_code="    def authenticate(self, username: str) -> bool:\n        return True",
            parent_class="AuthService",
        ),
    ]

    parsed_file = ParsedFile(
        file_path="src/auth.py",
        language="python",
        content_type=ContentType.CODE,
        raw_content=raw_code,
        symbols=symbols,
        total_lines=3,
    )

    chunks = chunk_code_file(parsed_file, repository_id="repo-123")

    assert len(chunks) >= 2

    # Check method chunk
    method_chunk = next(c for c in chunks if c.function_name == "authenticate")
    assert method_chunk.class_name == "AuthService"
    assert method_chunk.repository_id == "repo-123"
    assert method_chunk.file_path == "src/auth.py"
    assert method_chunk.language == "python"
    assert method_chunk.symbol_type == SymbolType.METHOD
    assert method_chunk.context_header is not None
    assert "class AuthService:" in method_chunk.context_header

    # Test metadata export for Qdrant payload
    payload = method_chunk.to_metadata_dict()
    assert payload["file_path"] == "src/auth.py"
    assert payload["function_name"] == "authenticate"
    assert payload["class_name"] == "AuthService"
    assert payload["content_type"] == "code"


def test_markdown_chunker_headers() -> None:
    """Test Markdown splitting along header sections."""
    doc = '''# Architecture Overview

This document describes the high-level architecture.

## Ingestion Pipeline

The ingestion pipeline scans, parses, and chunks code files.
It preserves AST metadata for citation generation.

## Vector Retrieval

Vector retrieval uses Qdrant with dense embeddings.
'''
    chunks = chunk_markdown(doc, file_path="docs/architecture.md", repository_id="repo-1")

    assert len(chunks) == 3

    titles = [c.section_title for c in chunks]
    assert "Architecture Overview" in titles
    assert "Ingestion Pipeline" in titles
    assert "Vector Retrieval" in titles

    for chunk in chunks:
        assert chunk.content_type == ContentType.DOCUMENTATION
        assert chunk.file_path == "docs/architecture.md"
        assert chunk.start_line is not None
        assert chunk.end_line is not None


def test_config_chunker() -> None:
    """Test configuration file chunker."""
    config_content = '''{
  "name": "ai-knowledge-agent",
  "version": "1.0.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build"
  }
}'''
    chunks = chunk_configuration(
        config_content,
        file_path="package.json",
        repository_id="repo-1",
    )

    assert len(chunks) == 1
    assert chunks[0].content_type == ContentType.CONFIGURATION
    assert chunks[0].file_path == "package.json"
    assert "ai-knowledge-agent" in chunks[0].content

