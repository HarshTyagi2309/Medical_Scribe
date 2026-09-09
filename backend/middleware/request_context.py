import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.logging import logger


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            duration_ms = round(
                (time.perf_counter() - start_time) * 1000,
                2,
            )

            logger.info(
                "%s %s status=%s duration_ms=%s request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
            )

            response.headers["X-Request-ID"] = request_id

            return response

        except Exception:
            duration_ms = round(
                (time.perf_counter() - start_time) * 1000,
                2,
            )

            logger.exception(
                "%s %s failed duration_ms=%s request_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
            )

            raise
