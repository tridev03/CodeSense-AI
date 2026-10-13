"""
Production observability, LLM tracing, and component latency monitoring.

Features:
- OBS-01: End-to-end request & retrieval stage tracing.
- OBS-02: Exception capture & error sanitization in spans.
- OBS-03: Retrieval stage telemetry (mode, top_k, candidate count, scores, IDs) without private code leaks.
- OBS-04: Component-level latency with monotonic clocks recorded into Prometheus metrics.
- OBS-05: Automated secret redaction on all metadata before SDK transmission.
- OBS-10: Bounded flush and resilient fallback to NoopTracer.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
import logging
import time
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional

from backend.config.settings import settings
from backend.observability.metrics import get_metrics_collector
from backend.observability.redaction import redact_string, redact_telemetry_data

logger = logging.getLogger(__name__)


class NoopSpan:
    """A no-op span that absorbs telemetry calls without performance overhead."""

    def __init__(self, name: str = "noop") -> None:
        self.name = name

    def end(self, **kwargs: Any) -> None:
        pass

    def update(self, **kwargs: Any) -> None:
        pass

    def score(self, **kwargs: Any) -> None:
        pass

    def event(self, **kwargs: Any) -> None:
        pass


class NoopTracer:
    """No-op tracer used when Langfuse is unconfigured or in test mode."""

    @contextmanager
    def span(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Generator[NoopSpan, None, None]:
        t0 = time.perf_counter()
        success = True
        try:
            yield NoopSpan(name)
        except Exception:
            success = False
            raise
        finally:
            elapsed = time.perf_counter() - t0
            get_metrics_collector().record_component_latency(name, elapsed, success=success)

    @asynccontextmanager
    async def aspan(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> AsyncGenerator[NoopSpan, None]:
        t0 = time.perf_counter()
        success = True
        try:
            yield NoopSpan(name)
        except Exception:
            success = False
            raise
        finally:
            elapsed = time.perf_counter() - t0
            get_metrics_collector().record_component_latency(name, elapsed, success=success)

    @contextmanager
    def trace_generation(
        self,
        name: str,
        model: str,
        input_data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator[NoopSpan, None, None]:
        t0 = time.perf_counter()
        success = True
        try:
            yield NoopSpan(name)
        except Exception:
            success = False
            raise
        finally:
            elapsed = time.perf_counter() - t0
            get_metrics_collector().record_component_latency(f"generation:{name}", elapsed, success=success)

    @contextmanager
    def trace_retrieval(
        self,
        name: str,
        query: str,
        top_k: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator[NoopSpan, None, None]:
        t0 = time.perf_counter()
        success = True
        try:
            yield NoopSpan(name)
        except Exception:
            success = False
            raise
        finally:
            elapsed = time.perf_counter() - t0
            get_metrics_collector().record_component_latency(f"retrieval:{name}", elapsed, success=success)

    def flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


class LangfuseTracer:
    """Wrapper around the Langfuse SDK for structured LLM and RAG telemetry with redaction."""

    def __init__(
        self,
        public_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        host: Optional[str] = None,
    ) -> None:
        self.public_key = public_key or settings.LANGFUSE_PUBLIC_KEY
        self.secret_key = secret_key or settings.LANGFUSE_SECRET_KEY
        self.host = host or settings.LANGFUSE_HOST
        self._client: Optional[Any] = None

        if self.public_key and self.secret_key and not settings.is_testing:
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    public_key=self.public_key,
                    secret_key=self.secret_key,
                    host=self.host,
                )
                logger.info("Langfuse observability initialized successfully | host=%s", self.host)
            except Exception as exc:
                logger.warning("Failed to initialize Langfuse client: %s. Using NoopTracer.", exc)
                self._client = None
        else:
            logger.debug("Langfuse keys not set or testing mode active. Tracing running in Noop mode.")

    @property
    def is_enabled(self) -> bool:
        return self._client is not None

    @contextmanager
    def span(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator[Any, None, None]:
        # Always redact metadata before sending to Langfuse (OBS-05)
        clean_meta = redact_telemetry_data(metadata or {})
        t0 = time.perf_counter()
        span_obj = None
        success = True
        try:
            if self._client:
                span_obj = self._client.span(name=name, metadata=clean_meta)
            yield span_obj if span_obj else NoopSpan(name)
        except Exception as exc:
            success = False
            # Record exception details safely in span (OBS-02)
            if span_obj and hasattr(span_obj, "update"):
                try:
                    span_obj.update(
                        level="ERROR",
                        status_message=redact_string(f"{type(exc).__name__}: {str(exc)}"),
                    )
                except Exception:
                    pass
            raise
        finally:
            elapsed = time.perf_counter() - t0
            get_metrics_collector().record_component_latency(name, elapsed, success=success)
            if span_obj and hasattr(span_obj, "end"):
                try:
                    span_obj.end(metadata={"latency_sec": elapsed, "success": success})
                except Exception:
                    pass

    @contextmanager
    def trace_generation(
        self,
        name: str,
        model: str,
        input_data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator[Any, None, None]:
        clean_input = redact_telemetry_data(input_data)
        clean_meta = redact_telemetry_data(metadata or {})
        t0 = time.perf_counter()
        generation = None
        success = True
        try:
            if self._client:
                generation = self._client.generation(
                    name=name,
                    model=model,
                    input=clean_input,
                    metadata=clean_meta,
                )
            yield generation if generation else NoopSpan(name)
        except Exception as exc:
            success = False
            if generation and hasattr(generation, "update"):
                try:
                    generation.update(
                        level="ERROR",
                        status_message=redact_string(f"{type(exc).__name__}: {str(exc)}"),
                    )
                except Exception:
                    pass
            raise
        finally:
            elapsed = time.perf_counter() - t0
            get_metrics_collector().record_component_latency(f"generation:{name}", elapsed, success=success)
            if generation and hasattr(generation, "end"):
                try:
                    generation.end(metadata={"latency_sec": elapsed, "success": success})
                except Exception:
                    pass

    @contextmanager
    def trace_retrieval(
        self,
        name: str,
        query: str,
        top_k: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator[Any, None, None]:
        """Instrument retrieval stage without leaking document bodies (OBS-03)."""
        meta = metadata or {}
        # Ensure query is sanitized and document summaries/IDs are used instead of raw bodies
        meta.update({
            "query": redact_string(query),
            "top_k": top_k,
        })
        with self.span(name=f"retrieval:{name}", metadata=meta) as s:
            yield s

    def flush(self) -> None:
        if self._client and hasattr(self._client, "flush"):
            try:
                self._client.flush()
            except Exception as exc:
                logger.warning("Error flushing Langfuse traces: %s", exc)

    def shutdown(self) -> None:
        if self._client and hasattr(self._client, "shutdown"):
            try:
                self._client.shutdown()
            except Exception as exc:
                logger.warning("Error shutting down Langfuse client: %s", exc)


_tracer_instance: Optional[LangfuseTracer | NoopTracer] = None


def get_tracer() -> LangfuseTracer | NoopTracer:
    """Return the global tracer instance."""
    global _tracer_instance
    if _tracer_instance is None:
        if (
            settings.is_testing
            or not settings.LANGFUSE_PUBLIC_KEY
            or not settings.LANGFUSE_SECRET_KEY
        ):
            _tracer_instance = NoopTracer()
        else:
            _tracer_instance = LangfuseTracer()
    return _tracer_instance
