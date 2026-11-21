"""Domain exception hierarchy — ARCHITECTURE.md §13. Every subcontext's exceptions.py
subclasses one of these; this is the only vocabulary for mapping a domain error to an
HTTP status (commons.adapters.api.exception_handler.status_for)."""


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


class DuplicatedTransactionError(ConflictError):
    pass


class ConcurrentModificationError(ConflictError):
    """A write lost a race against a concurrent write to the same aggregate — see
    ARCHITECTURE.md §8.1."""
