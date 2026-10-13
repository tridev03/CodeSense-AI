"""
Prometheus Metrics HTTP Middleware (OBS-04, OBS-07).

Measures HTTP request latency using monotonic clocks and counts status codes.
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.observability.metrics import get_metrics_collector


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that tracks request count and latency for all HTTP endpoints."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        t0 = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - t0
            # Record metrics, stripping query params to avoid cardinality bloat
            path = request.url.path
            # Do not record the /metrics endpoint itself to prevent self-loop skew
            if path != "/metrics":
                get_metrics_collector().record_http_request(
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration_s=elapsed,
                )
