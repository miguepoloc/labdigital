"""Request-scoped logging context — ARCHITECTURE.md §17.2. Sets the request_id contextvar
that commons.adapters.logs.JsonFormatter reads, so every log line inside a request is
correlated without threading a request id through every function signature."""

import uuid

import fastapi
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from backend.commons.adapters import logs


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: fastapi.Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        token = logs.request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            logs.request_id_var.reset(token)
        response.headers["X-Request-Id"] = request_id
        return response
