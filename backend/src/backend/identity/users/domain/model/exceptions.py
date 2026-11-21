from backend.commons.domain import exceptions


class UserNotFoundError(exceptions.NotFoundError):
    def __init__(self, *, identifier: object) -> None:
        super().__init__(f"User [{identifier}] not found.", code="USER_NOT_FOUND")


class UserAlreadyExistsError(exceptions.ConflictError):
    def __init__(self, *, email: object) -> None:
        super().__init__(f"A user with email [{email}] already exists.", code="USER_ALREADY_EXISTS")


class InvalidCredentialsError(exceptions.UnauthorizedError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password.", code="INVALID_CREDENTIALS")


class UserNotActiveError(exceptions.ForbiddenError):
    def __init__(self, *, user_id: object) -> None:
        super().__init__(f"User [{user_id}] is not active.", code="USER_NOT_ACTIVE")


class RefreshTokenNotFoundError(exceptions.UnauthorizedError):
    def __init__(self) -> None:
        super().__init__(
            "Refresh token is invalid, expired, or revoked.", code="INVALID_REFRESH_TOKEN"
        )
