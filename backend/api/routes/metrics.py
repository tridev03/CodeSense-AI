"""
Prometheus Metrics Exposition Endpoint (OBS-07).

Returns application and pipeline metrics formatted per the Prometheus / OpenMetrics standard.
"""
from __future__ import annotations

from fastapi import APIRouter, Response

from backend.observability.metrics import get_metrics_collector

router = APIRouter(tags=["observability"])


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Exposes application telemetry, HTTP metrics, and RAG component latencies in standard Prometheus format.",
    response_class=Response,
)
async def metrics_endpoint() -> Response:
    """Expose metrics in Prometheus text format."""
    data = get_metrics_collector().generate_prometheus_metrics()
    return Response(content=data, media_type="text/plain; version=0.0.4; charset=utf-8")
