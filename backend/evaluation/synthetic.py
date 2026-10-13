"""
Synthetic QA Pair Generator from repository code and document chunks.

Generates ground-truth evaluation pairs directly from indexed CodeChunk data:
- Function/Method chunks: "What does the function `{func_name}` in `{file_path}` do?"
- Class chunks: "Explain the purpose of class `{class_name}` in `{file_path}`."
- Documentation/Markdown chunks: "What is described in the `{section_title}` section of `{file_path}`?"
- Git history chunks: "When and why was commit `{commit_hash}` introduced by `{author}`?"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class SyntheticQAPair:
    """A synthetic ground-truth Q&A pair generated from an indexed repository chunk."""
    question: str
    ground_truth: str
    source_file: str
    chunk_id: Optional[str] = None
    symbol_name: Optional[str] = None
    content_type: str = "code"


def generate_synthetic_qa_from_chunks(
    chunks: Sequence[Dict[str, Any]],
    max_questions: int = 10,
) -> List[SyntheticQAPair]:
    """
    Generate diverse synthetic evaluation questions and ground truth answers from chunks.
    """
    qa_pairs: List[SyntheticQAPair] = []
    seen_symbols = set()

    for chunk in chunks:
        if len(qa_pairs) >= max_questions:
            break

        meta = chunk.get("metadata", {})
        content = chunk.get("content", "").strip()
        if not content or len(content) < 30:
            continue

        file_path = meta.get("file_path", chunk.get("file_path", "unknown"))
        content_type = meta.get("content_type", chunk.get("content_type", "code"))
        func_name = meta.get("function_name")
        class_name = meta.get("class_name")
        section_title = meta.get("section_title")
        commit_hash = meta.get("commit_hash")
        commit_author = meta.get("commit_author")

        # 1. Function / Method Chunk
        if func_name and func_name not in seen_symbols:
            seen_symbols.add(func_name)
            q = f"How is `{func_name}` implemented in `{file_path}` and what is its purpose?"
            gt = f"In `{file_path}`, `{func_name}` is defined as follows:\n{content[:400]}"
            qa_pairs.append(
                SyntheticQAPair(
                    question=q,
                    ground_truth=gt,
                    source_file=file_path,
                    chunk_id=chunk.get("id"),
                    symbol_name=func_name,
                    content_type="code",
                )
            )

        # 2. Class Chunk
        elif class_name and class_name not in seen_symbols:
            seen_symbols.add(class_name)
            q = f"What is the role of class `{class_name}` in `{file_path}`?"
            gt = f"The `{class_name}` class in `{file_path}` provides the following structure:\n{content[:400]}"
            qa_pairs.append(
                SyntheticQAPair(
                    question=q,
                    ground_truth=gt,
                    source_file=file_path,
                    chunk_id=chunk.get("id"),
                    symbol_name=class_name,
                    content_type="code",
                )
            )

        # 3. Markdown / Documentation Section
        elif content_type in ("markdown", "documentation") or section_title:
            title = section_title or file_path
            q = f"What details are documented in the `{title}` section of `{file_path}`?"
            gt = f"According to `{file_path}`, the `{title}` section explains:\n{content[:400]}"
            qa_pairs.append(
                SyntheticQAPair(
                    question=q,
                    ground_truth=gt,
                    source_file=file_path,
                    chunk_id=chunk.get("id"),
                    symbol_name=title,
                    content_type="markdown",
                )
            )

        # 4. Git Commit History
        elif content_type == "git_history" or commit_hash:
            c_hash = commit_hash or "recent commit"
            author = commit_author or "author"
            q = f"What changes and intent were recorded in commit `{c_hash}` by {author}?"
            gt = f"Commit `{c_hash}` by {author} contains the following log and changes:\n{content[:400]}"
            qa_pairs.append(
                SyntheticQAPair(
                    question=q,
                    ground_truth=gt,
                    source_file=file_path,
                    chunk_id=chunk.get("id"),
                    symbol_name=f"commit:{c_hash}",
                    content_type="git_history",
                )
            )

        # 5. Generic Code Chunk Fallback
        elif len(qa_pairs) < max_questions and file_path:
            start_line = meta.get("start_line", 1)
            end_line = meta.get("end_line", start_line + 10)
            q = f"What functionality is defined in `{file_path}` around lines {start_line}-{end_line}?"
            gt = f"In `{file_path}` (lines {start_line}-{end_line}), the code specifies:\n{content[:400]}"
            qa_pairs.append(
                SyntheticQAPair(
                    question=q,
                    ground_truth=gt,
                    source_file=file_path,
                    chunk_id=chunk.get("id"),
                    symbol_name=file_path,
                    content_type="code",
                )
            )

    return qa_pairs
