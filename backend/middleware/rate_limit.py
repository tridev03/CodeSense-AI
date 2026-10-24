"""
In-memory sliding-window Rate Limiter Middleware.

Protects API endpoints against denial of service and accidental hammering.
Returns HTTP 429 Too Many Requests when a client IP exceeds rate limits.
"""
from __future__ import annotations

import collections
import time
from typing import Any, Callable, DefaultDict, Deque, Optional

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config.settings import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window log rate limiter per client IP.

    Args:
        max_requests: Maximum allowed requests within the time window.
        window_seconds: Window size in seconds.
        enabled: Explicit toggle (defaults to True in production/development, False in testing unless overridden).
    """

    def __init__(
        self,
        app: Any,
        max_requests: int = 120,
        window_seconds: int = 60,
        enabled: Optional[bool] = None,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.enabled = (not settings.is_testing) if enabled is None else enabled
        self._requests: DefaultDict[str, Deque[float]] = collections.defaultdict(collections.deque)

    def _get_client_ip(self, request: Request) -> str:
        peer_ip = request.client.host if request.client else "unknown"
        trusted_proxies = set(getattr(settings, "TRUSTED_PROXIES", ["127.0.0.1", "::1", "localhost"]))

        # Only trust X-Forwarded-For if request directly arrived from a configured trusted proxy
        if peer_ip in trusted_proxies:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return peer_ip

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Skip rate limiting on docs and health check endpoints
        path = request.url.path
        if path in ("/health", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.time()
        client_timestamps = self._requests[client_ip]

        # Purge timestamps outside the current window
        cutoff = now - self.window_seconds
        while client_timestamps and client_timestamps[0] < cutoff:
            client_timestamps.popleft()

        if len(client_timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - client_timestamps[0])) + 1
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Please wait before retrying.",
                    "max_requests": self.max_requests,
                    "window_seconds": self.window_seconds,
                    "retry_after_seconds": max(1, retry_after),
                },
                headers={"Retry-After": str(max(1, retry_after))},
            )

        client_timestamps.append(now)
        return await call_next(request)
