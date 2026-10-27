"""
Sliding-window Rate Limiter Middleware.

Protects API endpoints against denial of service and accidental hammering.
Supports:
- Distributed Redis sliding window log for multi-instance deployments (when REDIS_URL configured)
- Automatic fallback to process-local in-memory sliding window when Redis is offline or unconfigured
- Trusted proxy verification to prevent IP spoofing via X-Forwarded-For
"""
from __future__ import annotations

import collections
import logging
import time
from typing import Any, Callable, DefaultDict, Deque, Optional, Tuple

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config.settings import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window log rate limiter per client IP.

    Args:
        max_requests: Maximum allowed requests within the time window.
        window_seconds: Window size in seconds.
        enabled: Explicit toggle (defaults to True in production/development, False in testing unless overridden).
        redis_client: Optional injected redis.asyncio.Redis instance.
    """

    def __init__(
        self,
        app: Any,
        max_requests: int = 120,
        window_seconds: int = 60,
        enabled: Optional[bool] = None,
        redis_client: Optional[Any] = None,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.enabled = (not settings.is_testing) if enabled is None else enabled
        self._requests: DefaultDict[str, Deque[float]] = collections.defaultdict(collections.deque)
        self._redis_client = redis_client

        if self._redis_client is None and getattr(settings, "REDIS_URL", None) and not settings.is_testing:
            try:
                import redis.asyncio as aioredis
                self._redis_client = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=False,
                    socket_connect_timeout=2.0,
                )
                logger.info("RateLimitMiddleware initialized with distributed Redis backend")
            except Exception as exc:
                logger.warning("Could not connect to Redis for rate limiting: %s. Using in-memory fallback.", exc)
                self._redis_client = None

    def _get_client_ip(self, request: Request) -> str:
        peer_ip = request.client.host if request.client else "unknown"
        trusted_proxies = set(getattr(settings, "TRUSTED_PROXIES", ["127.0.0.1", "::1", "localhost"]))

        # Only trust X-Forwarded-For if request directly arrived from a configured trusted proxy
        if peer_ip in trusted_proxies:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return peer_ip

    def _check_memory(self, client_ip: str, now: float) -> Tuple[bool, int]:
        """Check and record request using in-memory deque."""
        client_timestamps = self._requests[client_ip]
        cutoff = now - self.window_seconds
        while client_timestamps and client_timestamps[0] < cutoff:
            client_timestamps.popleft()

        if len(client_timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - client_timestamps[0])) + 1
            return False, max(1, retry_after)

        client_timestamps.append(now)
        return True, 0

    async def _check_redis(self, client_ip: str, now: float) -> Tuple[bool, int]:
        """Check and record request using Redis sorted set sliding window log."""
        key = f"ratelimit:{client_ip}"
        cutoff = now - self.window_seconds

        async with self._redis_client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            results = await pipe.execute()

        current_count = results[1]
        oldest_records = results[2]

        if current_count >= self.max_requests:
            if oldest_records:
                oldest_ts = float(oldest_records[0][1])
                retry_after = int(self.window_seconds - (now - oldest_ts)) + 1
            else:
                retry_after = self.window_seconds
            return False, max(1, retry_after)

        # Request allowed: persist timestamp in Redis sliding window
        async with self._redis_client.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {f"{now}:{time.monotonic_ns()}": now})
            pipe.expire(key, self.window_seconds + 5)
            await pipe.execute()

        return True, 0

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Skip rate limiting on docs and health check endpoints
        path = request.url.path
        if path in ("/health", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.time()

        allowed, retry_after = True, 0
        if self._redis_client is not None:
            try:
                allowed, retry_after = await self._check_redis(client_ip, now)
            except Exception as exc:
                logger.warning("Redis rate limit check error: %s. Falling back to in-memory.", exc)
                allowed, retry_after = self._check_memory(client_ip, now)
        else:
            allowed, retry_after = self._check_memory(client_ip, now)

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Please wait before retrying.",
                    "max_requests": self.max_requests,
                    "window_seconds": self.window_seconds,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
