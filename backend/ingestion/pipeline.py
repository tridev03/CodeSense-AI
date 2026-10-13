"""
End-to-end ingestion pipeline.

Orchestrates the full flow:
  Clone/Load → Scan → Parse → Chunk → Return chunks

This pipeline is called by the repository service when indexing is triggered.
In Phase 3, the output chunks will be sent to the embedding service and
stored in Qdrant. For now, chunks are returned as a list for testing
and verification.

The pipeline updates IndexingJob progress at each major step so the
frontend can display real-time status.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

from backend.ingestion.chunkers.code_chunker import chunk_code_file
from backend.ingestion.chunkers.doc_chunker import chunk_configuration, chunk_markdown
from backend.ingestion.cloner import (
    CloneResult,
    ClonerError,
    cleanup_clone,
    clone_repository,
    load_local_repository,
)
from backend.ingestion.models import (
    CodeChunk,
    ContentType,
    DiscoveredFile,
    ParsedFile,
)
from backend.ingestion.parsers.base import get_parser, register_parser
from backend.ingestion.parsers.fallback_parser import fallback_parser
from backend.ingestion.scanner import scan_repository

logger = logging.getLogger(__name__)


# ─── Parser Registration ─────────────────────────────────────────────────────

_parsers_initialized = False


def _ensure_parsers_registered() -> None:
    """
    Lazily register all available tree-sitter parsers.

    This is called once at pipeline startup. If a tree-sitter package
    is not installed, that language simply won't have a parser registered
    and the fallback parser will be used instead.
    """
    global _parsers_initialized
    if _parsers_initialized:
        return
    _parsers_initialized = True

    # Python parser
    try:
        from backend.ingestion.parsers.python_parser import PythonParser
        register_parser(PythonParser())
        logger.info("Python parser registered")
    except ImportError:
        logger.warning("tree-sitter-python not available; Python files will use fallback parser")

    # JavaScript/TypeScript parser
    try:
        from backend.ingestion.parsers.js_ts_parser import JsTsParser
        register_parser(JsTsParser())
        logger.info("JavaScript/TypeScript parser registered")
    except ImportError:
        logger.warning("tree-sitter-javascript/typescript not available; JS/TS files will use fallback parser")


# ─── File Parsing ─────────────────────────────────────────────────────────────


def _read_file_safe(file: DiscoveredFile) -> Optional[str]:
    """Read file content with encoding detection. Returns None on failure."""
    try:
        with open(file.absolute_path, "r", encoding=file.encoding, errors="replace") as f:
            return f.read()
    except Exception as exc:
        logger.warning("Failed to read file %s: %s", file.path, exc)
        return None


def _parse_file(file: DiscoveredFile, content: str) -> ParsedFile:
    """Parse a single file using the appropriate parser."""
    if file.content_type == ContentType.CODE and file.language:
        parser = get_parser(file.language)
        if parser:
            try:
                return parser.parse_file(
                    content,
                    language=file.language,
                    file_path=file.path,
                    content_type=file.content_type,
                )
            except Exception as exc:
                logger.warning(
                    "Tree-sitter parser failed for %s, falling back: %s",
                    file.path, exc,
                )

        # Fallback parser
        try:
            return fallback_parser.parse_file(
                content,
                language=file.language or "unknown",
                file_path=file.path,
                content_type=file.content_type,
            )
        except Exception as exc:
            logger.warning("Fallback parser failed for %s: %s", file.path, exc)

    # Non-code files or failed parsing — return as raw content
    total_lines = content.count("\n") + (1 if content else 0)
    return ParsedFile(
        file_path=file.path,
        language=file.language,
        content_type=file.content_type,
        raw_content=content,
        symbols=[],
        total_lines=total_lines,
    )


def _chunk_file(
    parsed: ParsedFile, *, repository_id: Optional[str] = None
) -> List[CodeChunk]:
    """Route a parsed file to the appropriate chunker and apply deterministic IDs (REL-02)."""
    if parsed.content_type == ContentType.CODE:
        chunks = chunk_code_file(parsed, repository_id=repository_id)
    elif parsed.content_type == ContentType.DOCUMENTATION:
        chunks = chunk_markdown(
            parsed.raw_content,
            file_path=parsed.file_path,
            repository_id=repository_id,
        )
    elif parsed.content_type == ContentType.CONFIGURATION:
        chunks = chunk_configuration(
            parsed.raw_content,
            file_path=parsed.file_path,
            repository_id=repository_id,
        )
    else:
        chunks = []

    # Enforce deterministic IDs for idempotent ingestion
    for chunk in chunks:
        chunk.ensure_deterministic_id(repository_id)

    return chunks


# ─── Pipeline ─────────────────────────────────────────────────────────────────


class IngestionResult:
    """Result of the ingestion pipeline."""

    def __init__(
        self,
        *,
        chunks: List[CodeChunk],
        files_discovered: int,
        files_processed: int,
        files_failed: int,
        clone_result: Optional[CloneResult] = None,
        duration_seconds: float = 0.0,
    ):
        self.chunks = chunks
        self.files_discovered = files_discovered
        self.files_processed = files_processed
        self.files_failed = files_failed
        self.clone_result = clone_result
        self.duration_seconds = duration_seconds

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    def __repr__(self) -> str:
        return (
            f"IngestionResult(files={self.files_processed}/{self.files_discovered}, "
            f"chunks={self.total_chunks}, failed={self.files_failed}, "
            f"duration={self.duration_seconds:.2f}s)"
        )


# Type alias for progress callbacks
ProgressCallback = Callable[[float, str], None]


def run_ingestion(
    url_or_path: str,
    *,
    is_local: bool = False,
    branch: Optional[str] = "main",
    repository_id: Optional[str] = None,
    max_file_size_mb: float = 5.0,
    progress_callback: Optional[ProgressCallback] = None,
) -> IngestionResult:
    """
    Run the complete ingestion pipeline.

    Args:
        url_or_path: GitHub HTTPS URL or absolute local path.
        is_local: True if url_or_path is a local directory.
        branch: Git branch to clone (ignored for local paths).
        repository_id: UUID string for the repository.
        max_file_size_mb: Maximum file size to process.
        progress_callback: Optional callback(progress_pct, step_description).

    Returns:
        IngestionResult with all chunks and statistics.

    Raises:
        ClonerError: If cloning/loading fails.
    """
    start_time = time.time()

    def _progress(pct: float, step: str) -> None:
        if progress_callback:
            progress_callback(pct, step)
        logger.info("Ingestion progress: %.1f%% — %s", pct, step)

    # ── Step 1: Ensure parsers are registered ──────────────────────────────
    _ensure_parsers_registered()

    # ── Step 2: Clone or Load ──────────────────────────────────────────────
    _progress(5.0, "Loading repository")
    clone_result: Optional[CloneResult] = None

    if is_local:
        clone_result = load_local_repository(url_or_path)
    else:
        clone_result = clone_repository(url_or_path, branch=branch)

    repo_root = clone_result.local_path

    try:
        # ── Step 3: Scan ───────────────────────────────────────────────────
        _progress(15.0, "Scanning repository files")
        discovered = scan_repository(
            repo_root, max_file_size_mb=max_file_size_mb
        )

        if not discovered:
            _progress(100.0, "No files found")
            return IngestionResult(
                chunks=[],
                files_discovered=0,
                files_processed=0,
                files_failed=0,
                clone_result=clone_result,
                duration_seconds=time.time() - start_time,
            )

        # ── Step 4: Parse & Chunk ──────────────────────────────────────────
        _progress(20.0, f"Processing {len(discovered)} files")

        all_chunks: List[CodeChunk] = []
        files_processed = 0
        files_failed = 0

        for i, file in enumerate(discovered):
            # Progress update every 10 files
            if i % 10 == 0 or i == len(discovered) - 1:
                pct = 20.0 + (i / len(discovered)) * 75.0
                _progress(pct, f"Processing file {i + 1}/{len(discovered)}: {file.path}")

            content = _read_file_safe(file)
            if content is None:
                files_failed += 1
                continue

            try:
                parsed = _parse_file(file, content)
                chunks = _chunk_file(parsed, repository_id=repository_id)
                all_chunks.extend(chunks)
                files_processed += 1
            except Exception as exc:
                logger.warning(
                    "Failed to process file %s: %s", file.path, exc
                )
                files_failed += 1

        _progress(100.0, "Ingestion complete")

        duration = time.time() - start_time
        result = IngestionResult(
            chunks=all_chunks,
            files_discovered=len(discovered),
            files_processed=files_processed,
            files_failed=files_failed,
            clone_result=clone_result,
            duration_seconds=duration,
        )

        logger.info("Ingestion completed: %s", result)
        return result

    finally:
        # Clean up cloned repos (not local ones)
        if clone_result and clone_result.is_cloned:
            cleanup_clone(clone_result.local_path)

