"""El único lugar donde se deciden los códigos HTTP — ARCHITECTURE.md §13.

Todas las respuestas de error siguen el contrato §6:
`{"error": {"code": "snake_case", "message": "texto en español", "details": {...}?}}`.
"""

from typing import Any

import fastapi
from fastapi import exceptions as fastapi_exceptions
from fastapi import responses, status
from starlette import exceptions as starlette_exceptions

from backend.commons.adapters import logs
from backend.commons.domain import exceptions

_LOGGER = logs.get_logger()

_STATUS_FOR: dict[type[exceptions.DomainError], int] = {
    exceptions.NotFoundError: status.HTTP_404_NOT_FOUND,
    exceptions.ConflictError: status.HTTP_409_CONFLICT,
    exceptions.ValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    exceptions.BadRequestError: status.HTTP_400_BAD_REQUEST,
    exceptions.UnauthorizedError: status.HTTP_401_UNAUTHORIZED,
    exceptions.ForbiddenError: status.HTTP_403_FORBIDDEN,
    exceptions.PayloadTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    exceptions.TooManyRequestsError: status.HTTP_429_TOO_MANY_REQUESTS,
}

# Para HTTPException que levanta el propio framework (rutas inexistentes, métodos).
_CODE_FOR_STATUS: dict[int, tuple[str, str]] = {
    status.HTTP_400_BAD_REQUEST: ("bad_request", "Petición inválida."),
    status.HTTP_401_UNAUTHORIZED: ("unauthenticated", "Sesión no válida o caducada."),
    status.HTTP_403_FORBIDDEN: ("forbidden", "No tienes permiso para esta acción."),
    status.HTTP_404_NOT_FOUND: ("not_found", "Recurso no encontrado."),
    status.HTTP_405_METHOD_NOT_ALLOWED: ("method_not_allowed", "Método no permitido."),
    status.HTTP_413_CONTENT_TOO_LARGE: (
        "payload_too_large",
        "El contenido supera el tamaño permitido.",
    ),
}


def status_for(error: exceptions.DomainError) -> int:
    for error_type, http_status in _STATUS_FOR.items():
        if isinstance(error, error_type):
            return http_status
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> responses.JSONResponse:
    """Construye una respuesta de error con la forma del contrato §6. Usado también por los
    middlewares (CSRF, tamaño de cuerpo), que no pasan por los exception handlers."""
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return responses.JSONResponse(status_code=status_code, content={"error": body}, headers=headers)


def install(app: fastapi.FastAPI) -> None:
    """Llamar una vez por app FastAPI."""

    @app.exception_handler(exceptions.DomainError)
    async def _handle_domain_error(
        _request: fastapi.Request, error: exceptions.DomainError
    ) -> responses.JSONResponse:
        headers: dict[str, str] | None = None
        if isinstance(error, exceptions.TooManyRequestsError):
            headers = {"Retry-After": str(error.retry_after_seconds)}
        http_status = status_for(error)
        details = dict(error.details)
        if http_status == status.HTTP_422_UNPROCESSABLE_CONTENT:
            details = _with_fields(details, str(error))
        if http_status >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            _LOGGER.error("Error de dominio no mapeado: %s (%s)", error.code, error)
        return error_response(
            status_code=http_status,
            code=error.code,
            message=str(error),
            details=details or None,
            headers=headers,
        )

    @app.exception_handler(fastapi_exceptions.RequestValidationError)
    async def _handle_validation_error(
        _request: fastapi.Request, error: fastapi_exceptions.RequestValidationError
    ) -> responses.JSONResponse:
        fields: dict[str, str] = {}
        for item in error.errors():
            loc = [
                str(part) for part in item.get("loc", ()) if part not in ("body", "query", "path")
            ]
            name = ".".join(loc) or "_"
            fields.setdefault(name, _spanish_message(str(item.get("type", ""))))
        return error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="Datos inválidos.",
            details={"fields": fields},
        )

    @app.exception_handler(starlette_exceptions.HTTPException)
    async def _handle_http_exception(
        _request: fastapi.Request, error: starlette_exceptions.HTTPException
    ) -> responses.JSONResponse:
        code, message = _CODE_FOR_STATUS.get(error.status_code, ("http_error", "Error."))
        return error_response(
            status_code=error.status_code,
            code=code,
            message=message,
            headers=dict(error.headers) if error.headers else None,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(
        _request: fastapi.Request, _error: Exception
    ) -> responses.JSONResponse:
        _LOGGER.exception("Error no controlado")
        return error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Error interno. Inténtalo más tarde.",
        )


_TYPE_MESSAGES = {
    "missing": "Campo obligatorio.",
    "string_too_long": "Texto demasiado largo.",
    "string_too_short": "Texto demasiado corto.",
    "string_type": "Debe ser un texto.",
    "bool_parsing": "Debe ser verdadero o falso.",
    "bool_type": "Debe ser verdadero o falso.",
    "int_parsing": "Debe ser un número entero.",
    "int_type": "Debe ser un número entero.",
    "dict_type": "Debe ser un objeto JSON.",
    "json_invalid": "JSON mal formado.",
    "model_attributes_type": "Debe ser un objeto JSON.",
}


def _spanish_message(error_type: str) -> str:
    return _TYPE_MESSAGES.get(error_type, "Valor no válido.")


def _with_fields(details: dict[str, Any], message: str) -> dict[str, Any]:
    """Contrato §6.1: un 422 lleva `details.fields = {campo: mensaje en español}`. Los
    errores de dominio declaran `details["field"]`; aquí se normaliza esa forma."""
    if "fields" in details:
        return details
    field = str(details.pop("field", "_"))
    return {"fields": {field: message}, **details}
