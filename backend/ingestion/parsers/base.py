"""
Abstract base parser interface.

All language-specific parsers implement this interface.
The parser registry maps language names to parser instances,
making it trivial to add new languages later.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type

from backend.ingestion.models import CodeSymbol, ContentType, ParsedFile

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """
    Abstract interface for a code parser.

    Subclasses must implement:
    - `supported_languages`: set of language name strings this parser handles.
    - `parse_symbols()`: extract CodeSymbol objects from source code.
    """

    @property
    @abstractmethod
    def supported_languages(self) -> set[str]:
        """Return the set of language strings this parser supports."""
        ...

    @abstractmethod
    def parse_symbols(
        self, source_code: str, *, language: str, file_path: str
    ) -> List[CodeSymbol]:
        """
        Extract structured symbols from source code.

        Args:
            source_code: The full text content of the file.
            language: The programming language identifier.
            file_path: Relative path (for error reporting).

        Returns:
            A list of CodeSymbol objects.
        """
        ...

    def parse_file(
        self,
        source_code: str,
        *,
        language: str,
        file_path: str,
        content_type: ContentType = ContentType.CODE,
    ) -> ParsedFile:
        """
        Parse a file and return a ParsedFile with symbols.

        This is the main entry point. Subclasses typically don't need to
        override this — they implement `parse_symbols()` instead.
        """
        symbols = self.parse_symbols(
            source_code, language=language, file_path=file_path
        )
        total_lines = source_code.count("\n") + (1 if source_code else 0)

        return ParsedFile(
            file_path=file_path,
            language=language,
            content_type=content_type,
            raw_content=source_code,
            symbols=symbols,
            total_lines=total_lines,
        )


# ─── Parser Registry ─────────────────────────────────────────────────────────

_registry: Dict[str, BaseParser] = {}


def register_parser(parser: BaseParser) -> None:
    """Register a parser instance for its supported languages."""
    for lang in parser.supported_languages:
        _registry[lang] = parser
        logger.debug("Registered parser for language: %s", lang)


def get_parser(language: str) -> Optional[BaseParser]:
    """Look up a registered parser by language name. Returns None if not found."""
    return _registry.get(language)


def get_all_supported_languages() -> set[str]:
    """Return the set of all languages with a registered parser."""
    return set(_registry.keys())

