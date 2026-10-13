"""
Unit tests for the LLM service and prompt/citation utilities.

Tests:
- Context block formatting
- Structured citation extraction
- Answer generation (mock and structured prompt)
"""
from __future__ import annotations

import pytest

from backend.llm import LLMService, extract_citations, format_context_blocks


def test_format_context_blocks() -> None:
    """Verify context formatting includes file paths, lines, and symbols."""
    chunks = [
        {
            "content": "def connect(): return True",
            "metadata": {
                "file_path": "src/db.py",
                "start_line": 10,
                "end_line": 20,
                "language": "python",
                "function_name": "connect",
                "symbol_type": "function",
            },
        }
    ]

    formatted = format_context_blocks(chunks)
    assert "src/db.py" in formatted
    assert "Lines 10-20" in formatted
    assert "function: connect" in formatted
    assert "def connect(): return True" in formatted


def test_extract_citations() -> None:
    """Verify citations are extracted accurately from chunks."""
    chunks = [
        {
            "content": "class AuthService:\n    def login(self): pass\n    def logout(self): pass",
            "metadata": {
                "file_path": "src/auth.py",
                "start_line": 1,
                "end_line": 15,
                "class_name": "AuthService",
            },
        }
    ]

    citations = extract_citations(chunks, "The AuthService handles logins.")
    assert len(citations) == 1
    assert citations[0].file_path == "src/auth.py"
    assert citations[0].start_line == 1
    assert citations[0].end_line == 15
    assert citations[0].symbol == "AuthService"
    assert "class AuthService:" in (citations[0].snippet or "")


@pytest.mark.asyncio
async def test_llm_service_generate_answer() -> None:
    """Verify answer generation with mock fallback returns answer and citation evidence."""
    service = LLMService()

    chunks = [
        {
            "content": "def authenticate(user, pwd): return True",
            "metadata": {
                "file_path": "src/auth/service.py",
                "start_line": 45,
                "end_line": 60,
                "function_name": "authenticate",
            },
        }
    ]

    answer, tokens = await service.generate_answer("How does authentication work?", chunks)
    assert isinstance(answer, str)
    assert len(answer) > 0
    assert "src/auth/service.py" in answer
    assert tokens is not None
    assert tokens > 0

