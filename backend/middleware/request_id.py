"""
Correlation ID / Request-ID Middleware.

Ensures every incoming HTTP request has a unique X-Request-ID:
1. Re-uses X-Request-ID from client header if provided.
2. Generates a new UUIDv4 if missing.
3. Attaches request_id to request.state.request_id.
4. Binds request_id to structlog contextvars for distributed log tracing.
5. Returns X-Request-ID in HTTP response headers.
"""
from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Starlette middleware for distributed request tracing with X-Request-ID."""

    HEADER_NAME = "X-Request-ID"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Extract or generate Request ID
        request_id = request.headers.get(self.HEADER_NAME) or str(uuid.uuid4())
        request.state.request_id = request_id

        # 2. Bind to structlog context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            # 3. Process request
            response = await call_next(request)
            # 4. Attach to response headers
            response.headers[self.HEADER_NAME] = request_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
