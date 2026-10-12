"""Log HTTP request, response, and timing fields without reading request bodies."""

from __future__ import annotations

import logging
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from fastapi import Request, Response

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status, elapsed time, and optional client address."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        include_client: bool = True,
        process_time_header: str = "X-Process-Time",
    ) -> None:
        """Configure client logging and the response timing header."""
        super().__init__(app)
        self.include_client = include_client
        self.process_time_header = process_time_header

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process a request, log its outcome, and add an elapsed-time header."""
        start = perf_counter()
        client = request.client.host if self.include_client and request.client else None
        fields: dict[str, object] = {
            "http.method": request.method,
            "http.path": request.url.path,
        }
        if client is not None:
            fields["client.address"] = client
        logger.info("HTTP request started", extra=fields)

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - start) * 1000
            logger.exception(
                "HTTP request failed",
                extra={**fields, "http.duration_ms": round(duration_ms, 3)},
            )
            raise

        duration_ms = (perf_counter() - start) * 1000
        response.headers[self.process_time_header] = f"{duration_ms:.1f}ms"
        logger.info(
            "HTTP response finished",
            extra={
                **fields,
                "http.status_code": response.status_code,
                "http.duration_ms": round(duration_ms, 3),
            },
        )
        return response


__all__ = ["LoggingMiddleware"]
