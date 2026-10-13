"""
Documentation and configuration file chunker.

Handles:
- Markdown files: splits by header hierarchy (# / ## / ###)
- ReStructuredText: splits by section headers
- Plain text: splits by paragraph / line count
- Configuration files: kept as single chunks (usually small)

Each chunk is tagged with section_title and content_type metadata.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from backend.ingestion.models import CodeChunk, ContentType

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_MAX_CHUNK_CHARS = 2000    # Max characters per documentation chunk
DEFAULT_OVERLAP_CHARS = 200       # Character overlap between chunks
MIN_CHUNK_CHARS = 50              # Minimum chars for a chunk to be worthwhile

# Markdown header pattern
_MD_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def chunk_markdown(
    content: str,
    *,
    file_path: str,
    repository_id: Optional[str] = None,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> List[CodeChunk]:
    """
    Split a Markdown document into chunks along header boundaries.

    Strategy:
    1. Split the document at each header line.
    2. Each section (header + content until next header) becomes a chunk.
    3. If a section is too long, further split by paragraphs.
    4. Section title is preserved in metadata for retrieval filtering.

    Args:
        content: Full markdown text.
        file_path: Relative path within the repository.
        repository_id: UUID string.
        max_chunk_chars: Maximum characters per chunk.

    Returns:
        List of CodeChunk objects with content_type=DOCUMENTATION.
    """
    if not content.strip():
        return []

    # Find all headers and their positions
    headers = list(_MD_HEADER_RE.finditer(content))

    if not headers:
        # No headers — chunk as plain text
        return _chunk_plain_text(
            content,
            file_path=file_path,
            repository_id=repository_id,
            max_chunk_chars=max_chunk_chars,
            content_type=ContentType.DOCUMENTATION,
        )

    chunks: List[CodeChunk] = []

    # Process each section
    for idx, header_match in enumerate(headers):
        section_title = header_match.group(2).strip()
        section_start = header_match.start()

        # Section ends at the next header or end of document
        if idx + 1 < len(headers):
            section_end = headers[idx + 1].start()
        else:
            section_end = len(content)

        section_text = content[section_start:section_end].strip()

        if len(section_text) < MIN_CHUNK_CHARS:
            continue

        # Calculate line numbers
        start_line = content[:section_start].count("\n") + 1
        end_line = content[:section_end].count("\n") + 1

        if len(section_text) <= max_chunk_chars:
            chunks.append(CodeChunk(
                repository_id=repository_id,
                file_path=file_path,
                content_type=ContentType.DOCUMENTATION,
                content=section_text,
                section_title=section_title,
                start_line=start_line,
                end_line=end_line,
            ))
        else:
            # Section is too long — split by paragraphs
            sub_chunks = _split_by_paragraphs(
                section_text,
                max_chars=max_chunk_chars,
                section_title=section_title,
            )
            for sub_text in sub_chunks:
                if len(sub_text.strip()) >= MIN_CHUNK_CHARS:
                    chunks.append(CodeChunk(
                        repository_id=repository_id,
                        file_path=file_path,
                        content_type=ContentType.DOCUMENTATION,
                        content=sub_text,
                        section_title=section_title,
                        start_line=start_line,
                        end_line=end_line,
                    ))

    # Handle content before the first header (preamble)
    if headers and headers[0].start() > 0:
        preamble = content[:headers[0].start()].strip()
        if len(preamble) >= MIN_CHUNK_CHARS:
            chunks.insert(0, CodeChunk(
                repository_id=repository_id,
                file_path=file_path,
                content_type=ContentType.DOCUMENTATION,
                content=preamble,
                section_title="Preamble",
                start_line=1,
                end_line=content[:headers[0].start()].count("\n") + 1,
            ))

    return chunks


def chunk_configuration(
    content: str,
    *,
    file_path: str,
    repository_id: Optional[str] = None,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> List[CodeChunk]:
    """
    Chunk a configuration file.

    Small configs (< max_chunk_chars) are kept as a single chunk.
    Larger configs are split at blank lines.

    Args:
        content: Full file content.
        file_path: Relative path.
        repository_id: UUID string.
        max_chunk_chars: Maximum characters per chunk.

    Returns:
        List of CodeChunk objects with content_type=CONFIGURATION.
    """
    if not content.strip():
        return []

    if len(content) <= max_chunk_chars:
        return [CodeChunk(
            repository_id=repository_id,
            file_path=file_path,
            content_type=ContentType.CONFIGURATION,
            content=content.strip(),
            start_line=1,
            end_line=content.count("\n") + 1,
        )]

    # Split at blank lines for larger configs
    return _chunk_plain_text(
        content,
        file_path=file_path,
        repository_id=repository_id,
        max_chunk_chars=max_chunk_chars,
        content_type=ContentType.CONFIGURATION,
    )


def _split_by_paragraphs(
    text: str, *, max_chars: int, section_title: str
) -> List[str]:
    """Split text into paragraph-aligned chunks."""
    paragraphs = re.split(r"\n\n+", text)
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _chunk_plain_text(
    content: str,
    *,
    file_path: str,
    repository_id: Optional[str] = None,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    content_type: ContentType = ContentType.DOCUMENTATION,
) -> List[CodeChunk]:
    """
    Split plain text or unstructured content by paragraph / character limit.
    """
    paragraphs = re.split(r"\n\n+", content)
    chunks: List[CodeChunk] = []
    current_text = ""
    current_start_line = 1
    line_counter = 1

    for para in paragraphs:
        para_lines = para.count("\n") + 1

        if len(current_text) + len(para) + 2 > max_chunk_chars and current_text.strip():
            end_line = line_counter - 1
            chunks.append(CodeChunk(
                repository_id=repository_id,
                file_path=file_path,
                content_type=content_type,
                content=current_text.strip(),
                start_line=current_start_line,
                end_line=end_line,
            ))
            current_text = para
            current_start_line = line_counter
        else:
            current_text = f"{current_text}\n\n{para}" if current_text else para

        line_counter += para_lines + 1  # +1 for blank line between paragraphs

    # Remaining text
    if current_text.strip() and len(current_text.strip()) >= MIN_CHUNK_CHARS:
        chunks.append(CodeChunk(
            repository_id=repository_id,
            file_path=file_path,
            content_type=content_type,
            content=current_text.strip(),
            start_line=current_start_line,
            end_line=line_counter,
        ))

    return chunks

