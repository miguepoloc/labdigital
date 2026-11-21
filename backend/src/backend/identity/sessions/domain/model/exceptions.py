from backend.commons.domain import exceptions


class RefreshTokenInvalidError(exceptions.UnauthorizedError):
    """Inválido, caducado, revocado, mal formado o reusado: un único error (no se distingue
    la causa ante el cliente)."""

    def __init__(self) -> None:
        super().__init__("La sesión no es válida o ha caducado.", code="token_invalid")


class SessionNotFoundError(exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__("Sesión no encontrada.", code="not_found")
