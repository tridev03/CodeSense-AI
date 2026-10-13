"""
Core evaluation metrics for RAG and LLM Generation.

Provides self-contained, deterministic Information Retrieval and Generation quality metrics:
- Faithfulness: Fraction of claims/sentences in the answer that are supported by the retrieved context.
- Answer Relevance: Semantic similarity between the user question and the generated answer.
- Context Recall: Extent to which ground truth statements are covered by retrieved context.
- Context Precision: Precision of retrieved chunks (penalizing irrelevant chunks placed high).
- Hallucination Rate: Fraction of answer sentences that have no grounding in retrieved context.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Set


def _tokenize(text: str) -> Set[str]:
    """Tokenize text into lowercase alphanumeric words."""
    return set(re.findall(r"\b\w{3,}\b", text.lower()))


def _token_overlap_ratio(set_a: Set[str], set_b: Set[str]) -> float:
    """Calculate token overlap with support for common prefixes (e.g. auth/authenticate)."""
    if not set_a or not set_b:
        return 0.0
    matches = 0
    for a in set_a:
        for b in set_b:
            if a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b[:4]) or b.startswith(a[:4]))):
                matches += 1
                break
    return matches / len(set_a)


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences/statements based on punctuation and linebreaks."""
    raw = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [s.strip() for s in raw if len(s.strip()) > 5]


def compute_faithfulness(
    answer: str,
    context_chunks: Sequence[Dict[str, Any]],
    overlap_threshold: float = 0.3,
) -> float:
    """
    Compute Faithfulness score (0.0 to 1.0).
    Measures the ratio of answer sentences that are grounded in the retrieved context chunks.
    """
    sentences = _split_sentences(answer)
    if not sentences:
        return 1.0

    combined_context = " ".join(
        c.get("content", "") if isinstance(c, dict) else str(c) for c in context_chunks
    ).lower()
    context_tokens = _tokenize(combined_context)

    if not context_tokens:
        return 0.0

    grounded_count = 0
    for sentence in sentences:
        sent_tokens = _tokenize(sentence)
        if not sent_tokens:
            continue
        overlap = sent_tokens.intersection(context_tokens)
        overlap_ratio = len(overlap) / len(sent_tokens)
        if overlap_ratio >= overlap_threshold:
            grounded_count += 1

    return min(1.0, max(0.0, grounded_count / len(sentences)))


def compute_hallucination_rate(
    answer: str,
    context_chunks: Sequence[Dict[str, Any]],
    overlap_threshold: float = 0.3,
) -> float:
    """
    Compute Hallucination Rate (0.0 to 1.0).
    Inverse of faithfulness: ratio of answer sentences not supported by context.
    """
    return 1.0 - compute_faithfulness(answer, context_chunks, overlap_threshold=overlap_threshold)


def compute_answer_relevance(
    question: str,
    answer: str,
    question_embedding: Optional[List[float]] = None,
    answer_embedding: Optional[List[float]] = None,
) -> float:
    """
    Compute Answer Relevance score (0.0 to 1.0).
    If embeddings are provided, uses cosine similarity.
    Otherwise, uses token Jaccard similarity and length heuristics.
    """
    if not answer.strip():
        return 0.0

    if question_embedding and answer_embedding and len(question_embedding) == len(answer_embedding):
        dot_product = sum(q * a for q, a in zip(question_embedding, answer_embedding))
        norm_q = math.sqrt(sum(q * q for q in question_embedding))
        norm_a = math.sqrt(sum(a * a for a in answer_embedding))
        if norm_q > 0 and norm_a > 0:
            cos_sim = dot_product / (norm_q * norm_a)
            # Map [-1, 1] to [0, 1]
            return min(1.0, max(0.0, (cos_sim + 1.0) / 2.0))

    q_tokens = _tokenize(question)
    a_tokens = _tokenize(answer)
    if not q_tokens or not a_tokens:
        return 0.0

    q_coverage = _token_overlap_ratio(q_tokens, a_tokens)
    a_coverage = _token_overlap_ratio(a_tokens, q_tokens)
    combined_score = 0.7 * q_coverage + 0.3 * a_coverage
    return min(1.0, max(0.0, combined_score))


def compute_context_recall(
    ground_truth: str,
    context_chunks: Sequence[Dict[str, Any]],
    overlap_threshold: float = 0.25,
) -> float:
    """
    Compute Context Recall score (0.0 to 1.0).
    Measures the fraction of ground truth statements present in the retrieved context.
    """
    sentences = _split_sentences(ground_truth)
    if not sentences:
        return 1.0

    combined_context = " ".join(
        c.get("content", "") if isinstance(c, dict) else str(c) for c in context_chunks
    ).lower()
    context_tokens = _tokenize(combined_context)

    if not context_tokens:
        return 0.0

    covered = 0
    for sentence in sentences:
        sent_tokens = _tokenize(sentence)
        if not sent_tokens:
            continue
        overlap = sent_tokens.intersection(context_tokens)
        if len(overlap) / len(sent_tokens) >= overlap_threshold:
            covered += 1

    return min(1.0, max(0.0, covered / len(sentences)))


def compute_context_precision(
    ground_truth: str,
    context_chunks: Sequence[Dict[str, Any]],
    overlap_threshold: float = 0.2,
) -> float:
    """
    Compute Context Precision score (0.0 to 1.0).
    Calculates weighted precision of retrieved chunks based on their relevance to ground truth.
    """
    if not context_chunks:
        return 0.0

    gt_tokens = _tokenize(ground_truth)
    if not gt_tokens:
        return 1.0

    hits = []
    for chunk in context_chunks:
        chunk_content = chunk.get("content", "") if isinstance(chunk, dict) else str(chunk)
        c_tokens = _tokenize(chunk_content)
        overlap = c_tokens.intersection(gt_tokens)
        is_relevant = (len(overlap) / len(gt_tokens) >= overlap_threshold) if gt_tokens else False
        hits.append(1 if is_relevant else 0)

    if sum(hits) == 0:
        return 0.0

    # Cumulative precision @ k
    precisions = []
    relevant_so_far = 0
    for k, hit in enumerate(hits, start=1):
        if hit:
            relevant_so_far += 1
            precisions.append(relevant_so_far / k)

    return sum(precisions) / len(precisions) if precisions else 0.0
