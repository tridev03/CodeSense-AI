"""
Prometheus-compatible service metrics and latency monitoring (OBS-04, OBS-07).

Provides:
- In-memory thread-safe metrics registry.
- Monotonic latency tracking for HTTP endpoints and RAG stages:
  - Embedding generation
  - BM25 retrieval
  - Vector search
  - Reciprocal Rank Fusion (RRF)
  - Cross-encoder reranking
  - LLM generation
- HTTP request counter and status histograms.
- OpenMetrics / Prometheus standard text format exporter (/metrics).
"""
from __future__ import annotations

from collections import defaultdict
import math
import threading
import time
from typing import Dict, List, Optional, Tuple


class MetricsCollector:
    """Thread-safe Prometheus-compatible metrics registry."""

    # Default histogram latency buckets (in seconds)
    LATENCY_BUCKETS: Tuple[float, ...] = (
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Counters: (name, label_tuple) -> float
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = defaultdict(float)
        # Gauges: (name, label_tuple) -> float
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = defaultdict(float)
        # Histograms: (name, label_tuple) -> {"buckets": Dict[float, int], "sum": float, "count": int}
        self._histograms: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, Any]] = {}

    def _labels_key(self, labels: Optional[Dict[str, str]]) -> Tuple[Tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(sorted((str(k), str(v)) for k, v in labels.items()))

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        key = (name, self._labels_key(labels))
        with self._lock:
            self._counters[key] += value

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        key = (name, self._labels_key(labels))
        with self._lock:
            self._gauges[key] = value

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        buckets: Tuple[float, ...] = LATENCY_BUCKETS,
    ) -> None:
        key = (name, self._labels_key(labels))
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = {
                    "buckets": {b: 0 for b in buckets},
                    "sum": 0.0,
                    "count": 0,
                }
            entry = self._histograms[key]
            entry["sum"] += value
            entry["count"] += 1
            for b in buckets:
                if value <= b:
                    entry["buckets"][b] += 1

    # ── Specific Domain Trackers ──────────────────────────────────────────────

    def record_http_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_s: float,
    ) -> None:
        """Record standard HTTP request metrics."""
        # Sanitize path to avoid high cardinality (e.g. collapse UUIDs)
        bounded_path = path
        labels = {
            "method": method.upper(),
            "path": bounded_path,
            "status": str(status_code),
        }
        self.increment_counter("http_requests_total", 1.0, labels)
        self.observe_histogram("http_request_duration_seconds", duration_s, {"method": method.upper(), "path": bounded_path})
        if status_code >= 500:
            self.increment_counter("http_requests_failed_total", 1.0, labels)

    def record_component_latency(
        self,
        stage: str,
        duration_s: float,
        success: bool = True,
    ) -> None:
        """
        Record internal RAG pipeline stage latency (OBS-04).
        Stages: embedding, bm25, vector_search, fusion, reranking, prompt, generation
        """
        labels = {"stage": stage, "status": "success" if success else "failure"}
        self.observe_histogram("rag_stage_duration_seconds", duration_s, labels)
        self.increment_counter("rag_stage_executions_total", 1.0, labels)

    def record_llm_tokens(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record token consumption (OBS-06)."""
        labels = {"model": model}
        if prompt_tokens > 0:
            self.increment_counter("llm_prompt_tokens_total", float(prompt_tokens), labels)
        if completion_tokens > 0:
            self.increment_counter("llm_completion_tokens_total", float(completion_tokens), labels)
        self.increment_counter("llm_total_tokens_total", float(prompt_tokens + completion_tokens), labels)

    # ── Prometheus Text Format Exporter ───────────────────────────────────────

    def generate_prometheus_metrics(self) -> str:
        """Generate output formatted per the Prometheus/OpenMetrics text specification."""
        lines: List[str] = [
            "# HELP http_requests_total Total number of HTTP requests processed",
            "# TYPE http_requests_total counter",
            "# HELP http_request_duration_seconds HTTP request latency histogram",
            "# TYPE http_request_duration_seconds histogram",
            "# HELP rag_stage_duration_seconds Internal RAG stage execution latency",
            "# TYPE rag_stage_duration_seconds histogram",
        ]

        with self._lock:
            # 1. Output counters
            for (name, labels), val in self._counters.items():
                label_str = ""
                if labels:
                    formatted = [f'{k}="{v}"' for k, v in labels]
                    label_str = "{" + ",".join(formatted) + "}"
                lines.append(f"{name}{label_str} {val}")

            # 2. Output gauges
            for (name, labels), val in self._gauges.items():
                label_str = ""
                if labels:
                    formatted = [f'{k}="{v}"' for k, v in labels]
                    label_str = "{" + ",".join(formatted) + "}"
                lines.append(f"{name}{label_str} {val}")

            # 3. Output histograms
            for (name, labels), hist in self._histograms.items():
                base_labels = dict(labels)
                # Buckets
                for b, count in sorted(hist["buckets"].items()):
                    b_str = "+Inf" if math.isinf(b) else str(b)
                    b_labels = dict(base_labels)
                    b_labels["le"] = b_str
                    lbl = "{" + ",".join([f'{k}="{v}"' for k, v in sorted(b_labels.items())]) + "}"
                    lines.append(f"{name}_bucket{lbl} {count}")
                # Count and sum
                base_lbl = ""
                if base_labels:
                    base_lbl = "{" + ",".join([f'{k}="{v}"' for k, v in sorted(base_labels.items())]) + "}"
                lines.append(f"{name}_count{base_lbl} {hist['count']}")
                lines.append(f"{name}_sum{base_lbl} {hist['sum']:.6f}")

        return "\n".join(lines) + "\n"


# Process-wide metrics registry singleton
_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Return the global MetricsCollector singleton."""
    return _metrics_collector
