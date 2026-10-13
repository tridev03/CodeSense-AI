"""
AST-driven code chunker.

Splits source code into semantically meaningful chunks based on parsed
code symbols (classes, methods, functions, imports).

Design principles:
- Each chunk represents a single logical code unit.
- Methods include their parent class context header for LLM comprehension.
- Large symbols (e.g., functions > max_chunk_lines) are split at safe
  boundaries while preserving the function signature as context.
- Every chunk carries full metadata for citation generation.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from backend.ingestion.models import (
    CodeChunk,
    CodeSymbol,
    ContentType,
    ParsedFile,
    SymbolType,
)

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_MAX_CHUNK_LINES = 150     # Lines above which a symbol is split
DEFAULT_OVERLAP_LINES = 5         # Lines of overlap between sub-chunks
MIN_CHUNK_LINES = 5              # Minimum lines to create a separate chunk


def _build_context_header(
    symbol: CodeSymbol,
    file_path: str,
    raw_content: str,
) -> Optional[str]:
    """
    Build a context header string for a method/function chunk.

    For methods: includes the class definition line.
    For standalone functions: includes file path context.

    This header is prepended to the chunk content so an LLM can understand
    where the code lives without seeing the full file.
    """
    lines = raw_content.splitlines()

    if symbol.parent_class and symbol.symbol_type == SymbolType.METHOD:
        # Find the class definition line
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"class {symbol.parent_class}"):
                return stripped
        # Fallback: just use the class name
        return f"class {symbol.parent_class}:"

    return None


def _extract_signature(source_code: str) -> str:
    """
    Extract the function/method signature (first line through the colon/brace).

    Used as context header when splitting large functions into sub-chunks.
    """
    lines = source_code.splitlines()
    sig_lines = []
    for line in lines:
        sig_lines.append(line)
        stripped = line.rstrip()
        if stripped.endswith(":") or stripped.endswith("{") or stripped.endswith(")"):
            break
    return "\n".join(sig_lines)


def _split_large_symbol(
    symbol: CodeSymbol,
    *,
    max_lines: int,
    overlap: int,
) -> List[str]:
    """
    Split a large symbol's source code into overlapping sub-chunks.

    Attempts to split at blank lines within the code for cleaner boundaries.
    Falls back to splitting at exact line counts if no blank lines are found.
    """
    lines = symbol.source_code.splitlines()
    if len(lines) <= max_lines:
        return [symbol.source_code]

    # Extract signature as context for sub-chunks
    signature = _extract_signature(symbol.source_code)
    sig_lines_count = len(signature.splitlines())

    chunks = []
    start = 0
    content_lines = lines

    while start < len(content_lines):
        end = min(start + max_lines, len(content_lines))

        # Try to find a blank line near the split point for a cleaner break
        if end < len(content_lines):
            best_split = end
            for j in range(end, max(start + max_lines // 2, start), -1):
                if j < len(content_lines) and content_lines[j].strip() == "":
                    best_split = j
                    break
            end = best_split

        chunk_text = "\n".join(content_lines[start:end])

        # Prepend signature as context for non-first chunks
        if start > 0:
            chunk_text = f"# ... continued from above\n{signature}\n    # ...\n{chunk_text}"

        chunks.append(chunk_text)

        # Move forward with overlap
        start = end - overlap if end < len(content_lines) else end

    return chunks


def chunk_code_file(
    parsed_file: ParsedFile,
    *,
    repository_id: Optional[str] = None,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
) -> List[CodeChunk]:
    """
    Convert a parsed code file into CodeChunks.

    Strategy:
    1. If the file has symbols from the AST parser:
       - Create one chunk per symbol (class, function, method, import block).
       - Methods include parent class context header.
       - Large symbols are split into overlapping sub-chunks.
    2. If no symbols were extracted (parser failed or unsupported):
       - Fall back to chunking the entire file by line count.

    Args:
        parsed_file: The ParsedFile from the parser stage.
        repository_id: UUID string of the repository.
        max_chunk_lines: Maximum lines before splitting a symbol.
        overlap_lines: Number of overlapping lines between sub-chunks.

    Returns:
        List of CodeChunk objects ready for embedding.
    """
    chunks: List[CodeChunk] = []

    if not parsed_file.symbols:
        # No symbols — chunk the raw file by line count
        return _chunk_raw_file(
            parsed_file,
            repository_id=repository_id,
            max_chunk_lines=max_chunk_lines,
            overlap_lines=overlap_lines,
        )

    # Track which line ranges are covered by symbols
    covered_lines = set()

    for symbol in parsed_file.symbols:
        # Skip tiny import blocks unless they're the only thing
        if symbol.symbol_type == SymbolType.IMPORT and len(parsed_file.symbols) > 1:
            # Include imports as a chunk but don't require a minimum size
            pass

        context_header = _build_context_header(
            symbol, parsed_file.file_path, parsed_file.raw_content
        )

        # Split large symbols
        sub_chunks = _split_large_symbol(
            symbol, max_lines=max_chunk_lines, overlap=overlap_lines
        )

        for i, chunk_text in enumerate(sub_chunks):
            # Determine function/class name for metadata
            func_name = None
            class_name = symbol.parent_class

            if symbol.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                func_name = symbol.name
            elif symbol.symbol_type == SymbolType.CLASS:
                class_name = symbol.name

            # Build the content with optional context header
            content = chunk_text
            if context_header and i == 0:
                # Prepend context header for methods (only first sub-chunk)
                content = f"# Context: {context_header}\n\n{chunk_text}"

            # Calculate line ranges for sub-chunks
            chunk_lines = len(chunk_text.splitlines())
            if len(sub_chunks) > 1:
                # Approximate line ranges for sub-chunks
                lines_per_chunk = (symbol.end_line - symbol.start_line + 1) / len(sub_chunks)
                start_line = symbol.start_line + int(i * lines_per_chunk)
                end_line = min(
                    symbol.start_line + int((i + 1) * lines_per_chunk) - 1,
                    symbol.end_line,
                )
            else:
                start_line = symbol.start_line
                end_line = symbol.end_line

            chunks.append(CodeChunk(
                repository_id=repository_id,
                file_path=parsed_file.file_path,
                language=parsed_file.language,
                content_type=ContentType.CODE,
                content=content,
                symbol_type=symbol.symbol_type,
                class_name=class_name,
                function_name=func_name,
                start_line=start_line,
                end_line=end_line,
                context_header=context_header,
            ))

            # Track covered lines
            for ln in range(symbol.start_line, symbol.end_line + 1):
                covered_lines.add(ln)

    # Check for uncovered top-level code
    _add_uncovered_chunks(
        parsed_file, covered_lines, chunks,
        repository_id=repository_id,
        max_chunk_lines=max_chunk_lines,
    )

    return chunks


def _chunk_raw_file(
    parsed_file: ParsedFile,
    *,
    repository_id: Optional[str] = None,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
) -> List[CodeChunk]:
    """Chunk a file with no AST symbols by line count with overlap."""
    lines = parsed_file.raw_content.splitlines()
    if not lines:
        return []

    chunks = []
    start = 0

    while start < len(lines):
        end = min(start + max_chunk_lines, len(lines))
        chunk_text = "\n".join(lines[start:end])

        if chunk_text.strip():  # Skip empty chunks
            chunks.append(CodeChunk(
                repository_id=repository_id,
                file_path=parsed_file.file_path,
                language=parsed_file.language,
                content_type=parsed_file.content_type,
                content=chunk_text,
                symbol_type=SymbolType.BLOCK,
                start_line=start + 1,
                end_line=end,
            ))

        start = end - overlap_lines if end < len(lines) else end

    return chunks


def _add_uncovered_chunks(
    parsed_file: ParsedFile,
    covered_lines: set,
    chunks: List[CodeChunk],
    *,
    repository_id: Optional[str] = None,
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES,
) -> None:
    """
    Add chunks for top-level code not covered by any extracted symbol.

    This catches module-level constants, global variables, and other
    executable code outside functions/classes.
    """
    lines = parsed_file.raw_content.splitlines()
    uncovered_start = None

    for i, line in enumerate(lines):
        line_num = i + 1
        if line_num not in covered_lines and line.strip():
            if uncovered_start is None:
                uncovered_start = i
        elif uncovered_start is not None and (line_num in covered_lines or not line.strip()):
            # End of uncovered block — only add if it has enough content
            block = lines[uncovered_start:i]
            content = "\n".join(block).strip()
            if content and len(block) >= MIN_CHUNK_LINES:
                chunks.append(CodeChunk(
                    repository_id=repository_id,
                    file_path=parsed_file.file_path,
                    language=parsed_file.language,
                    content_type=ContentType.CODE,
                    content=content,
                    symbol_type=SymbolType.BLOCK,
                    start_line=uncovered_start + 1,
                    end_line=i,
                ))
            uncovered_start = None

    # Handle trailing uncovered code
    if uncovered_start is not None:
        block = lines[uncovered_start:]
        content = "\n".join(block).strip()
        if content and len(block) >= MIN_CHUNK_LINES:
            chunks.append(CodeChunk(
                repository_id=repository_id,
                file_path=parsed_file.file_path,
                language=parsed_file.language,
                content_type=ContentType.CODE,
                content=content,
                symbol_type=SymbolType.BLOCK,
                start_line=uncovered_start + 1,
                end_line=len(lines),
            ))

