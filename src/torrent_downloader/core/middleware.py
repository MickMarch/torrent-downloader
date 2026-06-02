"""Request logging middleware: logs method, path, status, and duration for every request."""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from torrent_downloader.core.logger import app_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id

        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"

        app_logger.info(
            "%s %s %d %.1fms request_id=%s",
            request.method,
            path,
            response.status_code,
            duration_ms,
            request_id,
        )

        return response
