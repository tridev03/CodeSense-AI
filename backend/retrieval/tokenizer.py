"""
Code-aware tokenizer for BM25 and keyword retrieval.

Handles programming identifier conventions:
- snake_case: 'authenticate_user' -> ['authenticate', 'user', 'authenticate_user']
- camelCase / PascalCase: 'AuthService' -> ['auth', 'service', 'authservice']
- dotted/path identifiers: 'src/auth/service.py' -> ['src', 'auth', 'service', 'py']
- standard words and symbols
"""
from __future__ import annotations

import re
from typing import List, Set

# Regex to split camelCase and PascalCase
_CAMEL_CASE_RE = re.compile(r"([a-z0-9])([A-Z])")
_PASCAL_ACRONYM_RE = re.compile(r"([A-Z]+)([A-Z][a-z])")

# Punctuation to split on (code separators)
_CODE_SPLIT_RE = re.compile(r"[\s\.,;:/\\[\]\(\)\{\}<>=+\-*!&|#\"'`~?%^$@]+")


def split_identifier(ident: str) -> List[str]:
    """
    Split a single programming identifier into subwords while retaining the full word.

    Examples:
        'authenticate_user' -> ['authenticate', 'user', 'authenticate_user']
        'AuthService'       -> ['auth', 'service', 'authservice']
        'getUserById'       -> ['get', 'user', 'by', 'id', 'getuserbyid']
        'DBConnection'      -> ['db', 'connection', 'dbconnection']
    """
    if not ident:
        return []

    tokens: List[str] = []
    clean = ident.strip()

    # Split by snake_case / kebab-case
    parts = re.split(r"[_\-]+", clean)

    for part in parts:
        if not part:
            continue

        # Split PascalCase with acronyms: e.g. "DBConnection" -> "DB Connection"
        s = _PASCAL_ACRONYM_RE.sub(r"\1 \2", part)
        # Split camelCase: e.g. "authService" -> "auth Service"
        s = _CAMEL_CASE_RE.sub(r"\1 \2", s)

        subwords = s.split()
        for sw in subwords:
            sw_lower = sw.lower()
            if len(sw_lower) > 1:
                tokens.append(sw_lower)

        # Include the sub-token as a whole if multi-part
        part_lower = part.lower()
        if len(part_lower) > 1 and part_lower not in tokens:
            tokens.append(part_lower)

    # Include original identifier (lowercased, without delimiters)
    full_clean = re.sub(r"[_\-]+", "", clean).lower()
    if len(full_clean) > 1 and full_clean not in tokens:
        tokens.append(full_clean)

    return tokens


def tokenize_code(text: str) -> List[str]:
    """
    Tokenize a code snippet or natural language query for BM25.

    Returns a flat list of lowercased tokens with subwords preserved.
    """
    if not text:
        return []

    raw_tokens = _CODE_SPLIT_RE.split(text)
    final_tokens: List[str] = []

    for raw in raw_tokens:
        if not raw:
            continue
        # If it looks like an identifier, split subwords
        if "_" in raw or "-" in raw or any(c.isupper() for c in raw):
            final_tokens.extend(split_identifier(raw))
        else:
            token_lower = raw.lower()
            if len(token_lower) > 1:
                final_tokens.append(token_lower)

    return final_tokens

