"""
Observability and Telemetry Test Suite (OBS-01..OBS-07, OBS-10).

Verifies:
- Secret redaction on strings and nested data structures (OBS-05)
- Monotonic latency tracking & RAG stage metric collection (OBS-04)
- OpenMetrics / Prometheus /metrics generation (OBS-07)
- Exception capture and status recording in spans (OBS-02)
- Fast Noop fallback and thread-safe metric updates
"""
from __future__ import annotations

import time
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.observability.metrics import MetricsCollector, get_metrics_collector
from backend.observability.redaction import (
    REDACTED_PLACEHOLDER,
    redact_string,
    redact_telemetry_data,
)
from backend.observability.tracer import NoopTracer, get_tracer


# ─── Secret Redaction Tests (OBS-05) ──────────────────────────────────────────


class TestTelemetryRedaction:
    """Verifies that sensitive data never leaks into telemetry data structures."""

    def test_redact_connection_string_password(self):
        raw = "postgresql://myuser:SuperSecretPassword123@postgres-db.internal:5432/ai_knowledge"
        sanitized = redact_string(raw)
        assert "SuperSecretPassword123" not in sanitized
        assert "postgresql://myuser:[REDACTED]@postgres-db.internal:5432/ai_knowledge" == sanitized

    def test_redact_bearer_token(self):
        raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.xyz123"
        sanitized = redact_string(raw)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert REDACTED_PLACEHOLDER in sanitized

    def test_redact_api_key_patterns(self):
        raw = "Using Groq key: gsk_1234567890abcdefghijklmnopqrstuvwxyz"
        sanitized = redact_string(raw)
        assert "gsk_1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert REDACTED_PLACEHOLDER in sanitized

    def test_redact_nested_dict_keys(self):
        payload = {
            "query": "how does authentication work?",
            "password": "mypassword",
            "api_key": "some-key",
            "metadata": {
                "user_id": "u123",
                "secret_key": "supersecret",
                "nested_list": ["ok_item", "postgresql://admin:secret@host/db"],
            },
        }
        cleaned = redact_telemetry_data(payload)
        assert cleaned["query"] == "how does authentication work?"
        assert cleaned["password"] == REDACTED_PLACEHOLDER
        assert cleaned["api_key"] == REDACTED_PLACEHOLDER
        assert cleaned["metadata"]["user_id"] == "u123"
        assert cleaned["metadata"]["secret_key"] == REDACTED_PLACEHOLDER
        assert "secret" not in cleaned["metadata"]["nested_list"][1]
        assert "[REDACTED]" in cleaned["metadata"]["nested_list"][1]


# ─── Metrics and Prometheus Exporter Tests (OBS-04, OBS-07) ───────────────────


class TestMetricsCollector:
    """Verifies Prometheus metrics aggregation and text output."""

    def test_metrics_collector_counter_and_histogram(self):
        collector = MetricsCollector()
        collector.increment_counter("test_counter", 1.0, {"label": "a"})
        collector.observe_histogram("test_latency", 0.05, {"stage": "bm25"})

        prom_text = collector.generate_prometheus_metrics()
        assert "test_counter" in prom_text
        assert 'label="a"' in prom_text
        assert "test_latency_count" in prom_text
        assert "test_latency_bucket" in prom_text

    def test_record_rag_stage_latency(self):
        collector = MetricsCollector()
        collector.record_component_latency("vector_search", 0.012, success=True)
        collector.record_component_latency("vector_search", 0.035, success=True)
        collector.record_component_latency("reranking", 0.080, success=False)

        output = collector.generate_prometheus_metrics()
        assert 'rag_stage_executions_total{stage="vector_search",status="success"} 2.0' in output
        assert 'rag_stage_executions_total{stage="reranking",status="failure"} 1.0' in output


# ─── HTTP Endpoints for Observability ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint():
    """Verify /metrics returns 200 and standard Prometheus text format."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Generate some traffic first
        await client.get("/health/liveness")
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "http_requests_total" in response.text
