"""
LLM Service abstraction and Groq provider.

Provides grounded answer generation using retrieved context chunks with
strict citation rules. Supports Groq API (llama-3.3-70b-versatile) with
fallback to deterministic mock generation for offline/testing environments.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.config.settings import settings
from backend.schemas.rag import Citation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert AI Software Engineering Knowledge Agent.
Your job is to answer developer questions accurately using ONLY the provided repository context.

CRITICAL INSTRUCTIONS:
1. Answer using retrieved evidence from the code, documentation, and configuration files provided.
2. DO NOT hallucinate or invent functions, files, or facts that are not present in the context.
3. If the provided context is insufficient to answer the question completely, explicitly say what information is missing.
4. Distinguish verified facts found directly in code from your own inferences.
5. Always cite your sources using the format `[file_path#L{start}-L{end}]` or `[file_path]`. For example: `The authentication middleware is defined in [src/auth/service.py#L45-L80]`.
6. Provide clean code snippets when relevant to support your answer.
"""


def format_context_blocks(chunks: List[Dict[str, Any]]) -> str:
    """
    Format retrieved chunks into structured context blocks for the LLM prompt.
    """
    if not chunks:
        return "No relevant context found in repository."

    blocks = []
    for idx, c in enumerate(chunks, start=1):
        meta = c.get("metadata", {})
        content_type = meta.get("content_type", c.get("content_type", ""))
        content = c.get("content", "").strip()

        # Special formatting for Git commit history
        if content_type == "git_history" or meta.get("commit_hash"):
            c_hash = meta.get("commit_hash", "unknown")
            c_author = meta.get("commit_author", "unknown")
            c_date = meta.get("commit_date", "")
            block = f"--- Source [{idx}]: Git Commit {c_hash} by {c_author} ({c_date}) ---\n{content}\n"
            blocks.append(block)
            continue

        file_path = meta.get("file_path", c.get("file_path", "unknown"))
        start_line = meta.get("start_line", c.get("start_line"))
        end_line = meta.get("end_line", c.get("end_line"))
        language = meta.get("language", c.get("language", ""))
        symbol_type = meta.get("symbol_type", c.get("symbol_type", ""))
        symbol_name = meta.get("function_name") or meta.get("class_name") or meta.get("section_title") or ""

        loc_str = f"Lines {start_line}-{end_line}" if start_line and end_line else "Full file"
        sym_str = f" | {symbol_type}: {symbol_name}" if symbol_name else ""
        lang_str = f" | Language: {language}" if language else ""

        block = f"--- Source [{idx}]: {file_path} ({loc_str}{lang_str}{sym_str}) ---\n{content}\n"
        blocks.append(block)

    return "\n".join(blocks)


def extract_citations(chunks: List[Dict[str, Any]], answer_text: str) -> List[Citation]:
    """
    Extract structured citations based on retrieved chunks that support the answer.
    """
    citations: List[Citation] = []
    seen = set()

    for c in chunks:
        meta = c.get("metadata", {})
        content_type = meta.get("content_type", c.get("content_type", ""))
        content = c.get("content", "")

        if content_type == "git_history" or meta.get("commit_hash"):
            c_hash = meta.get("commit_hash", "")
            file_path = meta.get("file_path", "git/history")
            key = (file_path, c_hash)
            if key in seen:
                continue
            seen.add(key)

            lines = content.strip().splitlines()
            snippet = "\n".join(lines[:3]) if lines else None

            citations.append(
                Citation(
                    file_path=file_path,
                    start_line=None,
                    end_line=None,
                    symbol=f"commit:{c_hash}",
                    snippet=snippet,
                )
            )
            continue

        file_path = meta.get("file_path", c.get("file_path", ""))
        start_line = meta.get("start_line", c.get("start_line"))
        end_line = meta.get("end_line", c.get("end_line"))
        symbol = meta.get("function_name") or meta.get("class_name") or meta.get("section_title")

        key = (file_path, start_line, end_line)
        if key in seen:
            continue
        seen.add(key)

        # Snippet: first 2-3 lines of chunk content
        lines = content.strip().splitlines()
        snippet = "\n".join(lines[:3]) if lines else None

        citations.append(
            Citation(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                symbol=symbol,
                snippet=snippet,
            )
        )

    return citations


class LLMService:
    """
    Service for generating grounded answers using an LLM.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        self.temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        self.max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        self._client = None
        self._is_mock = False

    def _get_client(self):
        """Lazy-initialize Groq client."""
        if self._client is not None:
            return self._client

        if not self.api_key or settings.is_testing:
            self._is_mock = True
            return None

        try:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.api_key)
            logger.info("Initialized Groq client with model %s", self.model)
            return self._client
        except Exception as exc:
            logger.warning("Failed to initialize Groq client: %s. Using mock fallback.", exc)
            self._is_mock = True
            return None

    async def generate_answer(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
    ) -> Tuple[str, Optional[int]]:
        """
        Generate an answer to a query using context chunks.

        Returns:
            Tuple of (answer_text, tokens_used)
        """
        context_text = format_context_blocks(context_chunks)

        client = self._get_client()
        if self._is_mock or client is None:
            return self._generate_mock_answer(query, context_chunks)

        user_prompt = f"""Context from repository:
{context_text}

Question:
{query}

Please provide a detailed, accurate answer citing relevant files and line ranges:"""

        try:
            completion = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            answer = completion.choices[0].message.content or ""
            tokens = completion.usage.total_tokens if completion.usage else None
            return answer, tokens
        except Exception as exc:
            logger.error("Groq API call failed: %s. Falling back to mock generation.", exc)
            return self._generate_mock_answer(query, context_chunks)

    async def generate_answer_stream(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
    ):
        """
        Stream the answer token-by-token using Groq's streaming API.

        Yields string tokens. When the stream is exhausted the final token_usage
        is NOT yielded here — callers should track it separately if needed.
        Falls back to word-by-word mock streaming when Groq is unavailable.
        """
        context_text = format_context_blocks(context_chunks)

        client = self._get_client()
        if self._is_mock or client is None:
            # Mock: yield the pre-built answer word by word
            mock_answer, _ = self._generate_mock_answer(query, context_chunks)
            words = mock_answer.split(" ")
            for i, word in enumerate(words):
                yield word if i == 0 else " " + word
            return

        user_prompt = f"""Context from repository:\n{context_text}\n\nQuestion:\n{query}\n\nPlease provide a detailed, accurate answer citing relevant files and line ranges:"""

        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as exc:
            logger.error("Groq streaming API call failed: %s. Falling back to mock.", exc)
            mock_answer, _ = self._generate_mock_answer(query, context_chunks)
            words = mock_answer.split(" ")
            for i, word in enumerate(words):
                yield word if i == 0 else " " + word

    def _generate_mock_answer(
        self, query: str, context_chunks: List[Dict[str, Any]]
    ) -> Tuple[str, Optional[int]]:
        """
        Generate a structured deterministic answer when LLM is unavailable or in test mode.
        """
        if not context_chunks:
            return (
                f"I investigated the repository for '{query}', but no relevant code or documentation was found.",
                25,
            )

        top_chunk = context_chunks[0]
        meta = top_chunk.get("metadata", {})

        if meta.get("content_type") == "git_history" or meta.get("commit_hash"):
            c_hash = meta.get("commit_hash", "unknown")
            c_author = meta.get("commit_author", "unknown")
            c_date = meta.get("commit_date", "")
            return (
                f"Based on Git history analysis for '{query}':\n\n"
                f"The changes were introduced in commit [{c_hash}] by {c_author} on {c_date}. "
                f"Refer to the commit log and diff for full context.",
                45,
            )

        file_path = meta.get("file_path", top_chunk.get("file_path", "unknown"))
        start_line = meta.get("start_line", top_chunk.get("start_line", 1))
        end_line = meta.get("end_line", top_chunk.get("end_line", 10))
        symbol = meta.get("function_name") or meta.get("class_name") or meta.get("section_title") or "module"

        answer = (
            f"Based on the repository analysis for '{query}':\n\n"
            f"The implementation is located in [{file_path}#L{start_line}-L{end_line}] within `{symbol}`. "
            f"The codebase defines the relevant functionality as shown in the retrieved context."
        )
        return answer, 45


_llm_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Singleton getter for LLMService."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMService()
    return _llm_instance
