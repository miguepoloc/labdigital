"""Domain exception hierarchy — ARCHITECTURE.md §13. Every subcontext's exceptions.py
subclasses one of these; this is the only vocabulary for mapping a domain error to an
HTTP status (commons.adapters.api.exception_handler.status_for).

`code` es siempre `snake_case` y, cuando el frontend depende de él, uno de los códigos
fijos del contrato §6 (`invalid_credentials`, `version_conflict`, `not_found`, ...);
`message` va en español porque se muestra al usuario."""


class DomainError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retriable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retriable = retriable
        self.details = details or {}


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class UnauthorizedError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class BadRequestError(DomainError):
    pass


class PayloadTooLargeError(DomainError):
    def __init__(self, message: str = "El contenido supera el tamaño permitido.") -> None:
        super().__init__(message, code="payload_too_large")


class TooManyRequestsError(DomainError):
    """429 + `Retry-After` (contrato §6, `rate_limited`)."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__(
            "Demasiados intentos. Espera un momento e inténtalo de nuevo.",
            code="rate_limited",
            retriable=True,
        )
        self.retry_after_seconds = retry_after_seconds


class DuplicatedTransactionError(ConflictError):
    pass


class ConcurrentModificationError(ConflictError):
    """A write lost a race against a concurrent write to the same aggregate — see
    ARCHITECTURE.md §8.1."""
