"""
Fallback parser for unsupported languages or files where tree-sitter fails.

This parser does NOT use any AST — it works purely on text structure.
It uses indentation heuristics and common patterns to identify likely
function/class definitions across most languages.

The output is intentionally less precise than tree-sitter parsers, but
it ensures the ingestion pipeline never crashes on an unsupported file.
"""
from __future__ import annotations

import re
import logging
from typing import List

from backend.ingestion.models import CodeSymbol, SymbolType
from backend.ingestion.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# Common patterns for function/class definitions across languages
_FUNCTION_PATTERNS = [
    # Python: def name(...)
    re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\("),
    # JS/TS/Java/C#: function name(...) or type name(...)
    re.compile(r"^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\("),
    # Go: func name(...)
    re.compile(r"^(\s*)func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\("),
    # Rust: fn name(...)
    re.compile(r"^(\s*)(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"),
    # Ruby: def name
    re.compile(r"^(\s*)def\s+(\w+)"),
]

_CLASS_PATTERNS = [
    # Python/JS/TS/Java/C#: class Name
    re.compile(r"^(\s*)(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"),
    # Rust: struct Name or impl Name
    re.compile(r"^(\s*)(?:pub\s+)?(?:struct|impl|enum|trait)\s+(\w+)"),
    # Go: type Name struct
    re.compile(r"^(\s*)type\s+(\w+)\s+struct"),
]


class FallbackParser(BaseParser):
    """
    Generic text-based parser using regex patterns and indentation.

    Acts as the "catch all" — used when no tree-sitter parser is available
    for the file's language.
    """

    @property
    def supported_languages(self) -> set[str]:
        # This parser handles everything not covered by specialized parsers.
        # It is NOT registered in the registry — it's used as a fallback.
        return set()

    def parse_symbols(
        self, source_code: str, *, language: str, file_path: str
    ) -> List[CodeSymbol]:
        lines = source_code.splitlines()
        symbols: List[CodeSymbol] = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Try class patterns
            matched = False
            for pattern in _CLASS_PATTERNS:
                m = pattern.match(line)
                if m:
                    indent = len(m.group(1))
                    name = m.group(2)
                    end = self._find_block_end(lines, i, indent)
                    source = "\n".join(lines[i:end + 1])
                    symbols.append(CodeSymbol(
                        name=name,
                        symbol_type=SymbolType.CLASS,
                        start_line=i + 1,
                        end_line=end + 1,
                        source_code=source,
                    ))
                    matched = True
                    break

            if not matched:
                # Try function patterns
                for pattern in _FUNCTION_PATTERNS:
                    m = pattern.match(line)
                    if m:
                        indent = len(m.group(1))
                        name = m.group(2)
                        end = self._find_block_end(lines, i, indent)
                        source = "\n".join(lines[i:end + 1])
                        symbols.append(CodeSymbol(
                            name=name,
                            symbol_type=SymbolType.FUNCTION,
                            start_line=i + 1,
                            end_line=end + 1,
                            source_code=source,
                        ))
                        break

            i += 1

        return symbols

    @staticmethod
    def _find_block_end(lines: List[str], start: int, indent: int) -> int:
        """
        Find the end of a code block starting at `start` with base `indent`.

        Uses indentation: the block ends when a non-empty line at the same
        or lesser indentation level is found (or end of file).

        For brace-delimited languages, also tracks brace balance.
        """
        end = start
        brace_count = 0
        has_braces = False

        for j in range(start, len(lines)):
            line = lines[j]
            stripped = line.strip()

            # Track braces
            brace_count += stripped.count("{") - stripped.count("}")
            if "{" in stripped:
                has_braces = True

            if has_braces:
                # Brace-delimited: block ends when braces balance
                if j > start and brace_count <= 0:
                    return j
            else:
                # Indentation-delimited: block ends at same/lower indent
                if j > start and stripped and not stripped.startswith("#"):
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent <= indent:
                        return end

            if stripped:
                end = j

        return end


# Module-level singleton
fallback_parser = FallbackParser()

