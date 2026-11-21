"""The only place HTTP status codes get decided — ARCHITECTURE.md §13."""

import fastapi
from fastapi import responses

from backend.commons.domain import exceptions

_STATUS_FOR: dict[type[exceptions.DomainError], int] = {
    exceptions.NotFoundError: fastapi.status.HTTP_404_NOT_FOUND,
    exceptions.ConflictError: fastapi.status.HTTP_409_CONFLICT,
    exceptions.ValidationError: fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
    exceptions.UnauthorizedError: fastapi.status.HTTP_401_UNAUTHORIZED,
    exceptions.ForbiddenError: fastapi.status.HTTP_403_FORBIDDEN,
}


def status_for(error: exceptions.DomainError) -> int:
    for error_type, status in _STATUS_FOR.items():
        if isinstance(error, error_type):
            return status
    return fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR


def install(app: fastapi.FastAPI) -> None:
    """Call once per FastAPI app (each entrypoints/web/*.py Lambda) — ARCHITECTURE.md §9.1."""

    @app.exception_handler(exceptions.DomainError)
    async def _handle_domain_error(
        _request: fastapi.Request, error: exceptions.DomainError
    ) -> responses.JSONResponse:
        return responses.JSONResponse(
            status_code=status_for(error),
            content={"code": error.code, "message": str(error), "details": error.details},
        )
