"""
backend.observability module.

Provides production tracing and telemetry via Langfuse with graceful no-op fallback
when credentials are not configured or when running in test environments.
"""
from backend.observability.metrics import (
    MetricsCollector,
    get_metrics_collector,
)
from backend.observability.redaction import (
    redact_string,
    redact_telemetry_data,
)
from backend.observability.tracer import (
    LangfuseTracer,
    NoopSpan,
    NoopTracer,
    get_tracer,
)

__all__ = [
    "LangfuseTracer",
    "NoopSpan",
    "NoopTracer",
    "get_tracer",
    "MetricsCollector",
    "get_metrics_collector",
    "redact_string",
    "redact_telemetry_data",
]

