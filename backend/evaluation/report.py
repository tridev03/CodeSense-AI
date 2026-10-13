"""
Evaluation Report Formatter.

Formats evaluation results into clean Markdown and structured JSON summaries.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence
from backend.schemas.evaluation import MetricScores, QuestionEvaluationItem


def format_markdown_eval_report(
    repository_id: str,
    retrieval_mode: str,
    model: str,
    aggregate_scores: MetricScores,
    per_question: Sequence[QuestionEvaluationItem],
) -> str:
    """Format evaluation results as a readable Markdown report with metrics table."""
    lines = [
        f"# RAG Generation Evaluation Report",
        f"",
        f"- **Repository ID**: `{repository_id}`",
        f"- **Retrieval Mode**: `{retrieval_mode}`",
        f"- **Generation Model**: `{model}`",
        f"- **Evaluated Questions**: {len(per_question)}",
        f"",
        f"## 📊 Aggregate Metric Summary",
        f"",
        f"| Metric | Score | Rating | Target |",
        f"| :--- | :---: | :---: | :---: |",
        f"| **Faithfulness** | `{aggregate_scores.faithfulness:.4f}` | {_rate(aggregate_scores.faithfulness, 0.8, 0.6)} | $\\ge 0.80$ |",
        f"| **Answer Relevance** | `{aggregate_scores.answer_relevance:.4f}` | {_rate(aggregate_scores.answer_relevance, 0.75, 0.55)} | $\\ge 0.75$ |",
        f"| **Context Recall** | `{aggregate_scores.context_recall:.4f}` | {_rate(aggregate_scores.context_recall, 0.8, 0.6)} | $\\ge 0.80$ |",
        f"| **Context Precision** | `{aggregate_scores.context_precision:.4f}` | {_rate(aggregate_scores.context_precision, 0.7, 0.5)} | $\\ge 0.70$ |",
        f"| **Hallucination Rate** | `{aggregate_scores.hallucination_rate:.4f}` | {_rate_inverse(aggregate_scores.hallucination_rate, 0.15, 0.35)} | $\\le 0.15$ |",
        f"",
        f"## 📝 Per-Question Breakdown",
        f"",
    ]

    for idx, item in enumerate(per_question, start=1):
        lines.extend([
            f"### Question {idx}: {item.question}",
            f"- **Source**: `{item.source_file or 'General'}`",
            f"- **Faithfulness**: `{item.scores.faithfulness:.2f}` | **Relevance**: `{item.scores.answer_relevance:.2f}` | **Context Recall**: `{item.scores.context_recall:.2f}`",
            f"- **Generated Answer Preview**:",
            f"  > {item.generated_answer[:250].replace(chr(10), ' ')}...",
            f"",
        ])

    return "\n".join(lines)


def _rate(score: float, good_threshold: float, fair_threshold: float) -> str:
    if score >= good_threshold:
        return "🟢 Good"
    elif score >= fair_threshold:
        return "🟡 Moderate"
    return "🔴 Needs Improvement"


def _rate_inverse(score: float, good_threshold: float, fair_threshold: float) -> str:
    if score <= good_threshold:
        return "🟢 Low (Good)"
    elif score <= fair_threshold:
        return "🟡 Moderate"
    return "🔴 High (Needs Attention)"
