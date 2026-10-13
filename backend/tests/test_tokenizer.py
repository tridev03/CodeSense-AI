"""
Unit tests for code-aware tokenizer.

Tests:
- snake_case splitting
- camelCase and PascalCase splitting
- Acronym preservation in PascalCase (e.g. DBConnection)
- Delimiter splitting and punctuation stripping
"""
from __future__ import annotations

from backend.retrieval.tokenizer import split_identifier, tokenize_code


def test_split_identifier_snake_case() -> None:
    """Verify snake_case identifiers are split into subwords while keeping the whole token."""
    tokens = split_identifier("authenticate_user")
    assert "authenticate" in tokens
    assert "user" in tokens
    assert "authenticateuser" in tokens or "authenticate_user" in tokens


def test_split_identifier_camel_and_pascal_case() -> None:
    """Verify camelCase and PascalCase identifiers are split properly."""
    pascal_tokens = split_identifier("AuthService")
    assert "auth" in pascal_tokens
    assert "service" in pascal_tokens
    assert "authservice" in pascal_tokens

    camel_tokens = split_identifier("getUserById")
    assert "get" in camel_tokens
    assert "user" in camel_tokens
    assert "by" in camel_tokens
    assert "id" in camel_tokens


def test_split_identifier_acronyms() -> None:
    """Verify PascalCase with acronyms is handled correctly."""
    tokens = split_identifier("DBConnection")
    assert "db" in tokens
    assert "connection" in tokens


def test_tokenize_code_snippet() -> None:
    """Verify code tokenizer extracts symbols and path tokens."""
    code = "from src.auth.service import AuthService\ndef login(): pass"
    tokens = tokenize_code(code)

    assert "src" in tokens
    assert "auth" in tokens
    assert "service" in tokens
    assert "authservice" in tokens
    assert "login" in tokens

