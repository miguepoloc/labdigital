"""Middlewares HTTP compartidos — ARCHITECTURE.md §17.2 y contrato §2.

- `RequestLoggingMiddleware`: fija el `request_id` que lee `logs.JsonFormatter`.
- `CsrfMiddleware`: toda petición que no sea GET/HEAD/OPTIONS debe traer
  `X-Requested-With: labdigital` y un `Origin` del mismo host; si no ⇒ 403 `csrf_rejected`.
  Complementa a `SameSite` de las cookies (defensa en profundidad).
- `BodySizeLimitMiddleware`: rechaza con 413 `payload_too_large` cuerpos cuyo
  `Content-Length` supera el máximo (nginx aplica además `client_max_body_size`).
"""

from urllib import parse
import uuid

import fastapi
from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from backend.commons.adapters import logs, settings
from backend.commons.adapters.api import exception_handler

CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "labdigital"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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


def is_same_origin(*, origin: str | None, host: str | None, public_origin: str) -> bool:
    """`Origin` aceptado si coincide con el origen público configurado o si su host[:puerto]
    es exactamente la cabecera `Host` de la petición (nginx la reenvía con `$host`)."""
    if not origin or origin == "null":
        return False
    if origin.rstrip("/") == public_origin:
        return True
    netloc = parse.urlsplit(origin).netloc
    return bool(host) and netloc.lower() == (host or "").lower()


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: fastapi.Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in _SAFE_METHODS:
            header_ok = request.headers.get(CSRF_HEADER) == CSRF_HEADER_VALUE
            origin_ok = is_same_origin(
                origin=request.headers.get("origin"),
                host=request.headers.get("host"),
                public_origin=settings.get_settings().public_origin,
            )
            if not (header_ok and origin_ok):
                return exception_handler.error_response(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="csrf_rejected",
                    message="Petición rechazada por protección CSRF.",
                )
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """`overrides`: límites propios por `(método, sufijo de ruta)`, p. ej. la subida de
    archivos (`("POST", "/v1/files")` ⇒ 25 MB). El sufijo se compara con el final de la
    ruta, así vale con y sin el prefijo `/labdigital/api`."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        overrides: dict[tuple[str, str], int] | None = None,
    ) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes
        self._overrides = overrides or {}

    def _limit_for(self, method: str, path: str) -> int:
        for (override_method, suffix), limit in self._overrides.items():
            if method == override_method and path.rstrip("/").endswith(suffix):
                return limit
        return self._max_bytes

    async def dispatch(
        self, request: fastapi.Request, call_next: RequestResponseEndpoint
    ) -> Response:
        content_length = request.headers.get("content-length")
        limit = self._limit_for(request.method, request.url.path)
        if content_length is not None and content_length.isdigit() and int(content_length) > limit:
            return exception_handler.error_response(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                code="payload_too_large",
                message="El contenido supera el tamaño permitido.",
            )
        return await call_next(request)
