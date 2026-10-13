"""
Tree-sitter based JavaScript and TypeScript parser.

Uses the modern tree-sitter ≥0.23 API with official wheels:
- tree-sitter-javascript (for .js, .jsx, .mjs, .cjs)
- tree-sitter-typescript (for .ts, .tsx)

Extracts:
- ES6 classes and their methods
- Standalone functions (function declarations)
- Arrow functions assigned to variables/consts
- Exported functions/classes
- Async functions
- TypeScript interfaces and type aliases (as class-like symbols)
- Imports (grouped)

Tree-sitter node types (JS/TS grammars):
- program: root node
- class_declaration: class Foo {}
- function_declaration: function bar() {}
- lexical_declaration: const x = () => {}
- variable_declaration: var/let x = ...
- export_statement: export default/named ...
- import_statement: import ... from ...
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from backend.ingestion.models import CodeSymbol, SymbolType
from backend.ingestion.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# Lazy-loaded parsers — one per language variant
_parsers: Dict[str, Tuple] = {}


def _get_parser(language: str):
    """
    Lazy-initialize tree-sitter parser for the given JS/TS language.

    The tree-sitter-typescript package provides two sub-languages:
    - typescript (for .ts files)
    - tsx (for .tsx files)

    We use 'typescript' for both .ts since TSX is a superset.
    """
    if language in _parsers:
        return _parsers[language]

    try:
        from tree_sitter import Language, Parser

        if language in ("javascript",):
            import tree_sitter_javascript as ts_js
            lang = Language(ts_js.language())
        elif language in ("typescript",):
            import tree_sitter_typescript as ts_ts
            # tree-sitter-typescript exposes .language_typescript() and .language_tsx()
            # Use tsx parser since it's a superset of ts
            if hasattr(ts_ts, "language_tsx"):
                lang = Language(ts_ts.language_tsx())
            else:
                lang = Language(ts_ts.language())
        else:
            raise ValueError(f"Unsupported JS/TS language: {language}")

        parser = Parser(lang)
        _parsers[language] = (parser, lang)
        logger.info("Tree-sitter %s parser initialized", language)
        return parser, lang

    except ImportError as e:
        raise ImportError(
            f"tree-sitter and tree-sitter-{language} are required. "
            f"Install with: pip install tree-sitter tree-sitter-{language}"
        ) from e


def _get_text(node, source_bytes: bytes) -> str:
    """Extract source text for a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_child(node, type_name: str):
    """Find the first child of a specific type."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _find_children(node, type_name: str):
    """Find all children of a specific type."""
    return [child for child in node.children if child.type == type_name]


def _get_function_params(node, source_bytes: bytes) -> Optional[str]:
    """Extract parameter list from a function or method."""
    params = _find_child(node, "formal_parameters")
    if params:
        return _get_text(params, source_bytes)
    return None


def _get_jsdoc(node, source_bytes: bytes) -> Optional[str]:
    """Extract JSDoc comment preceding a node."""
    # Look at previous sibling for comment nodes
    prev = node.prev_named_sibling
    if prev and prev.type == "comment":
        text = _get_text(prev, source_bytes).strip()
        if text.startswith("/**"):
            # Strip /** and */ delimiters
            text = text[3:]
            if text.endswith("*/"):
                text = text[:-2]
            return text.strip()
    return None


class JsTsParser(BaseParser):
    """
    Tree-sitter based JavaScript/TypeScript symbol extractor.

    Handles ES6 classes, functions, arrow functions, exports, and TS interfaces.
    """

    @property
    def supported_languages(self) -> set[str]:
        return {"javascript", "typescript"}

    def parse_symbols(
        self, source_code: str, *, language: str, file_path: str
    ) -> List[CodeSymbol]:
        parser, lang = _get_parser(language)

        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)

        symbols: List[CodeSymbol] = []

        # Extract imports
        self._extract_imports(tree.root_node, source_bytes, symbols)

        # Walk top-level nodes
        self._walk_top_level(tree.root_node, source_bytes, symbols)

        return symbols

    def _extract_imports(
        self, root_node, source_bytes: bytes, symbols: List[CodeSymbol]
    ) -> None:
        """Group import statements into a single symbol."""
        import_lines = []
        import_start = None
        import_end = None

        for child in root_node.children:
            if child.type == "import_statement":
                text = _get_text(child, source_bytes)
                import_lines.append(text)
                if import_start is None:
                    import_start = child.start_point[0] + 1
                import_end = child.end_point[0] + 1

        if import_lines:
            symbols.append(CodeSymbol(
                name="imports",
                symbol_type=SymbolType.IMPORT,
                start_line=import_start,
                end_line=import_end,
                source_code="\n".join(import_lines),
            ))

    def _walk_top_level(
        self, root_node, source_bytes: bytes, symbols: List[CodeSymbol]
    ) -> None:
        """Walk top-level nodes extracting classes and functions."""
        for child in root_node.children:
            # Unwrap export statements
            if child.type == "export_statement":
                self._handle_export(child, source_bytes, symbols)
            elif child.type == "class_declaration":
                self._extract_class(child, source_bytes, symbols)
            elif child.type == "function_declaration":
                self._extract_function(child, source_bytes, symbols, parent_class=None)
            elif child.type in ("lexical_declaration", "variable_declaration"):
                self._extract_arrow_functions(child, source_bytes, symbols)
            # TypeScript-specific
            elif child.type == "interface_declaration":
                self._extract_interface(child, source_bytes, symbols)
            elif child.type == "type_alias_declaration":
                self._extract_type_alias(child, source_bytes, symbols)

    def _handle_export(
        self, node, source_bytes: bytes, symbols: List[CodeSymbol]
    ) -> None:
        """Handle export default/named statements by unwrapping to the actual declaration."""
        for child in node.children:
            if child.type == "class_declaration":
                self._extract_class(child, source_bytes, symbols, outer_node=node)
            elif child.type == "function_declaration":
                self._extract_function(child, source_bytes, symbols, parent_class=None, outer_node=node)
            elif child.type in ("lexical_declaration", "variable_declaration"):
                self._extract_arrow_functions(child, source_bytes, symbols, outer_node=node)
            elif child.type == "interface_declaration":
                self._extract_interface(child, source_bytes, symbols, outer_node=node)
            elif child.type == "type_alias_declaration":
                self._extract_type_alias(child, source_bytes, symbols, outer_node=node)

    def _extract_class(
        self,
        node,
        source_bytes: bytes,
        symbols: List[CodeSymbol],
        outer_node=None,
    ) -> None:
        """Extract a class declaration and its methods."""
        outer = outer_node or node
        name_node = _find_child(node, "identifier") or _find_child(node, "type_identifier")
        if not name_node:
            return

        class_name = _get_text(name_node, source_bytes)
        docstring = _get_jsdoc(outer, source_bytes)

        symbols.append(CodeSymbol(
            name=class_name,
            symbol_type=SymbolType.CLASS,
            start_line=outer.start_point[0] + 1,
            end_line=outer.end_point[0] + 1,
            source_code=_get_text(outer, source_bytes),
            docstring=docstring,
        ))

        # Extract methods from class body
        body = _find_child(node, "class_body")
        if body:
            for member in body.children:
                if member.type == "method_definition":
                    self._extract_method(member, source_bytes, symbols, class_name)

    def _extract_method(
        self, node, source_bytes: bytes, symbols: List[CodeSymbol], class_name: str
    ) -> None:
        """Extract a class method."""
        name_node = _find_child(node, "property_identifier")
        if not name_node:
            return

        method_name = _get_text(name_node, source_bytes)
        params = _get_function_params(node, source_bytes)
        docstring = _get_jsdoc(node, source_bytes)

        symbols.append(CodeSymbol(
            name=method_name,
            symbol_type=SymbolType.METHOD,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=_get_text(node, source_bytes),
            parent_class=class_name,
            parameters=params,
            docstring=docstring,
        ))

    def _extract_function(
        self,
        node,
        source_bytes: bytes,
        symbols: List[CodeSymbol],
        parent_class: Optional[str],
        outer_node=None,
    ) -> None:
        """Extract a function declaration."""
        outer = outer_node or node
        name_node = _find_child(node, "identifier")
        if not name_node:
            return

        func_name = _get_text(name_node, source_bytes)
        params = _get_function_params(node, source_bytes)
        docstring = _get_jsdoc(outer, source_bytes)

        symbols.append(CodeSymbol(
            name=func_name,
            symbol_type=SymbolType.METHOD if parent_class else SymbolType.FUNCTION,
            start_line=outer.start_point[0] + 1,
            end_line=outer.end_point[0] + 1,
            source_code=_get_text(outer, source_bytes),
            parent_class=parent_class,
            parameters=params,
            docstring=docstring,
        ))

    def _extract_arrow_functions(
        self,
        node,
        source_bytes: bytes,
        symbols: List[CodeSymbol],
        outer_node=None,
    ) -> None:
        """
        Extract arrow functions and anonymous function expressions
        assigned to variables: const foo = () => {} or const bar = function() {}
        """
        outer = outer_node or node
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = _find_child(child, "identifier")
                if not name_node:
                    continue

                # Check if the value is an arrow_function or function expression
                value = None
                for sub in child.children:
                    if sub.type in ("arrow_function", "function", "function_expression"):
                        value = sub
                        break

                if value is None:
                    continue

                func_name = _get_text(name_node, source_bytes)
                params = _get_function_params(value, source_bytes)
                docstring = _get_jsdoc(outer, source_bytes)

                symbols.append(CodeSymbol(
                    name=func_name,
                    symbol_type=SymbolType.FUNCTION,
                    start_line=outer.start_point[0] + 1,
                    end_line=outer.end_point[0] + 1,
                    source_code=_get_text(outer, source_bytes),
                    parameters=params,
                    docstring=docstring,
                ))

    def _extract_interface(
        self,
        node,
        source_bytes: bytes,
        symbols: List[CodeSymbol],
        outer_node=None,
    ) -> None:
        """Extract a TypeScript interface declaration."""
        outer = outer_node or node
        name_node = _find_child(node, "type_identifier") or _find_child(node, "identifier")
        if not name_node:
            return

        symbols.append(CodeSymbol(
            name=_get_text(name_node, source_bytes),
            symbol_type=SymbolType.CLASS,  # Treat interfaces as class-like for retrieval
            start_line=outer.start_point[0] + 1,
            end_line=outer.end_point[0] + 1,
            source_code=_get_text(outer, source_bytes),
            docstring=_get_jsdoc(outer, source_bytes),
        ))

    def _extract_type_alias(
        self,
        node,
        source_bytes: bytes,
        symbols: List[CodeSymbol],
        outer_node=None,
    ) -> None:
        """Extract a TypeScript type alias declaration."""
        outer = outer_node or node
        name_node = _find_child(node, "type_identifier") or _find_child(node, "identifier")
        if not name_node:
            return

        symbols.append(CodeSymbol(
            name=_get_text(name_node, source_bytes),
            symbol_type=SymbolType.CLASS,
            start_line=outer.start_point[0] + 1,
            end_line=outer.end_point[0] + 1,
            source_code=_get_text(outer, source_bytes),
            docstring=_get_jsdoc(outer, source_bytes),
        ))

