"""
Tree-sitter based Python code parser.

Uses the modern tree-sitter ≥0.23 API with official tree-sitter-python wheels.

Extracts:
- Module-level imports (grouped)
- Classes (with their methods)
- Standalone functions
- Async functions/methods
- Decorators
- Docstrings
- Parameter signatures
- Exact line spans

Tree-sitter node types reference (Python grammar):
- module: root node
- class_definition: class Foo:
- function_definition: def bar():
- decorated_definition: @decorator ...
- import_statement: import x
- import_from_statement: from x import y
"""
from __future__ import annotations

import logging
from typing import List, Optional

from backend.ingestion.models import CodeSymbol, SymbolType
from backend.ingestion.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# Lazy-loaded tree-sitter objects
_parser = None
_language = None


def _get_parser():
    """Lazy-initialize tree-sitter Python parser."""
    global _parser, _language
    if _parser is not None:
        return _parser, _language

    try:
        import tree_sitter_python as ts_python
        from tree_sitter import Language, Parser

        _language = Language(ts_python.language())
        _parser = Parser(_language)
        logger.info("Tree-sitter Python parser initialized successfully")
        return _parser, _language
    except ImportError as e:
        raise ImportError(
            "tree-sitter and tree-sitter-python are required. "
            "Install with: pip install tree-sitter tree-sitter-python"
        ) from e


def _get_text(node, source_bytes: bytes) -> str:
    """Extract the source text for a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _get_docstring(body_node, source_bytes: bytes) -> Optional[str]:
    """
    Extract docstring from a class/function body.

    In Python AST, a docstring is the first expression_statement child
    whose child is a string node.
    """
    if body_node is None:
        return None

    for child in body_node.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    text = _get_text(sub, source_bytes)
                    # Strip quotes
                    for quote in ('"""', "'''", '"', "'"):
                        if text.startswith(quote) and text.endswith(quote):
                            return text[len(quote):-len(quote)].strip()
                    return text.strip()
            break  # Only check the first expression_statement
        elif child.type == "comment":
            continue  # Skip leading comments
        else:
            break  # Not a docstring

    return None


def _get_decorators(node, source_bytes: bytes) -> List[str]:
    """Extract decorator names from a decorated_definition or function/class node."""
    decorators = []

    # If this node is wrapped in a decorated_definition, look at the parent
    parent = node.parent
    if parent and parent.type == "decorated_definition":
        for child in parent.children:
            if child.type == "decorator":
                decorators.append(_get_text(child, source_bytes).strip())

    return decorators


def _get_parameters(node, source_bytes: bytes) -> Optional[str]:
    """Extract the parameter list from a function definition."""
    for child in node.children:
        if child.type == "parameters":
            return _get_text(child, source_bytes)
    return None


def _get_body_node(node):
    """Get the body/block node of a class or function."""
    for child in node.children:
        if child.type == "block":
            return child
    return None


class PythonParser(BaseParser):
    """
    Tree-sitter based Python symbol extractor.

    Handles nested classes/functions with correct parent tracking.
    """

    @property
    def supported_languages(self) -> set[str]:
        return {"python"}

    def parse_symbols(
        self, source_code: str, *, language: str, file_path: str
    ) -> List[CodeSymbol]:
        parser, lang = _get_parser()

        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)

        symbols: List[CodeSymbol] = []

        # Collect import blocks
        self._extract_imports(tree.root_node, source_bytes, symbols)

        # Walk top-level for classes and functions
        self._walk_node(
            tree.root_node, source_bytes, symbols, parent_class=None
        )

        return symbols

    def _extract_imports(
        self, root_node, source_bytes: bytes, symbols: List[CodeSymbol]
    ) -> None:
        """Group consecutive import statements into a single IMPORT symbol."""
        import_lines = []
        import_start = None
        import_end = None

        for child in root_node.children:
            if child.type in ("import_statement", "import_from_statement"):
                text = _get_text(child, source_bytes)
                import_lines.append(text)
                if import_start is None:
                    import_start = child.start_point[0] + 1
                import_end = child.end_point[0] + 1
            elif import_lines and child.type not in ("comment", "newline"):
                # End of import block
                if import_lines:
                    symbols.append(CodeSymbol(
                        name="imports",
                        symbol_type=SymbolType.IMPORT,
                        start_line=import_start,
                        end_line=import_end,
                        source_code="\n".join(import_lines),
                    ))
                    import_lines = []
                    import_start = None
                    import_end = None

        # Trailing imports
        if import_lines:
            symbols.append(CodeSymbol(
                name="imports",
                symbol_type=SymbolType.IMPORT,
                start_line=import_start,
                end_line=import_end,
                source_code="\n".join(import_lines),
            ))

    def _walk_node(
        self,
        node,
        source_bytes: bytes,
        symbols: List[CodeSymbol],
        parent_class: Optional[str],
    ) -> None:
        """
        Recursively walk AST nodes and extract classes and functions.
        """
        for child in node.children:
            actual_node = child

            # Unwrap decorated_definition to get the actual class/function
            if child.type == "decorated_definition":
                for sub in child.children:
                    if sub.type in ("class_definition", "function_definition"):
                        actual_node = sub
                        break
                else:
                    continue

            if actual_node.type == "class_definition":
                self._extract_class(
                    actual_node, child, source_bytes, symbols, parent_class
                )
            elif actual_node.type == "function_definition":
                self._extract_function(
                    actual_node, child, source_bytes, symbols, parent_class
                )

    def _extract_class(
        self,
        class_node,
        outer_node,  # May be decorated_definition wrapping the class
        source_bytes: bytes,
        symbols: List[CodeSymbol],
        parent_class: Optional[str],
    ) -> None:
        """Extract a class and its methods."""
        # Get class name
        name_node = None
        for child in class_node.children:
            if child.type == "identifier":
                name_node = child
                break
        if name_node is None:
            return

        class_name = _get_text(name_node, source_bytes)
        body = _get_body_node(class_node)
        docstring = _get_docstring(body, source_bytes)
        decorators = _get_decorators(class_node, source_bytes)

        # Use outer_node (decorated_definition) for line range if available
        start_line = outer_node.start_point[0] + 1
        end_line = outer_node.end_point[0] + 1

        symbols.append(CodeSymbol(
            name=class_name,
            symbol_type=SymbolType.CLASS,
            start_line=start_line,
            end_line=end_line,
            source_code=_get_text(outer_node, source_bytes),
            parent_class=parent_class,
            docstring=docstring,
            decorators=decorators,
        ))

        # Extract methods from class body
        if body:
            self._walk_node(body, source_bytes, symbols, parent_class=class_name)

    def _extract_function(
        self,
        func_node,
        outer_node,
        source_bytes: bytes,
        symbols: List[CodeSymbol],
        parent_class: Optional[str],
    ) -> None:
        """Extract a function or method."""
        name_node = None
        for child in func_node.children:
            if child.type == "identifier":
                name_node = child
                break
        if name_node is None:
            return

        func_name = _get_text(name_node, source_bytes)
        body = _get_body_node(func_node)
        docstring = _get_docstring(body, source_bytes)
        decorators = _get_decorators(func_node, source_bytes)
        parameters = _get_parameters(func_node, source_bytes)

        start_line = outer_node.start_point[0] + 1
        end_line = outer_node.end_point[0] + 1

        symbol_type = SymbolType.METHOD if parent_class else SymbolType.FUNCTION

        symbols.append(CodeSymbol(
            name=func_name,
            symbol_type=symbol_type,
            start_line=start_line,
            end_line=end_line,
            source_code=_get_text(outer_node, source_bytes),
            parent_class=parent_class,
            docstring=docstring,
            decorators=decorators,
            parameters=parameters,
        ))

