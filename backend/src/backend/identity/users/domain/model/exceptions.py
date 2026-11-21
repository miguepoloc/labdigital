"""Errores de `identity.users`. Los `code` son los fijos del contrato §6 cuando el
frontend depende de ellos."""

from backend.commons.domain import exceptions


class UserNotFoundError(exceptions.NotFoundError):
    def __init__(self, *, identifier: object) -> None:
        super().__init__(f"Usuario [{identifier}] no encontrado.", code="not_found")


class UserAlreadyExistsError(exceptions.ConflictError):
    """Nunca llega al cliente: el registro responde 202 igual exista o no el correo."""

    def __init__(self) -> None:
        super().__init__("El correo ya está registrado.", code="email_taken")


class InvalidCredentialsError(exceptions.UnauthorizedError):
    def __init__(self) -> None:
        super().__init__("Correo o contraseña incorrectos.", code="invalid_credentials")


class EmailNotVerifiedError(exceptions.ForbiddenError):
    def __init__(self) -> None:
        super().__init__(
            "Debes verificar tu correo antes de entrar. Revisa tu bandeja de entrada.",
            code="email_not_verified",
        )


class AccountInactiveError(exceptions.ForbiddenError):
    def __init__(self) -> None:
        super().__init__("La cuenta está desactivada.", code="account_inactive")


class InvalidEmailTokenError(exceptions.BadRequestError):
    """Enlace de verificación/recuperación inexistente, caducado o ya usado — un solo error
    para todo (no se distingue cuál)."""

    def __init__(self) -> None:
        super().__init__("El enlace no es válido o ha caducado.", code="token_invalid")


class CurrentPasswordMismatchError(exceptions.BadRequestError):
    """400 y nunca 401 (contrato §6.1): un 401 haría que el frontend intente renovar."""

    def __init__(self) -> None:
        super().__init__("La contraseña actual no es correcta.", code="invalid_current_password")


class DataPolicyNotAcceptedError(exceptions.ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "Debes aceptar la política de tratamiento de datos.",
            code="validation_error",
            details={"field": "accept_data_policy"},
        )


class StaleCredentialsError(exceptions.UnauthorizedError):
    """El access es válido criptográficamente pero el usuario ya no está activo o cambió su
    `credentials_version` (contraseña restablecida/cambiada)."""

    def __init__(self) -> None:
        super().__init__("Sesión no válida o caducada.", code="unauthenticated")


class AdminRequiredError(exceptions.ForbiddenError):
    def __init__(self) -> None:
        super().__init__("Sólo un administrador puede hacer esto.", code="forbidden")


class CannotModifySelfError(exceptions.ConflictError):
    """Un admin no se desactiva ni se quita el rol a sí mismo (evita quedarse sin admins)."""

    def __init__(self) -> None:
        super().__init__(
            "No puedes desactivarte ni cambiar tu propio rol.", code="cannot_modify_self"
        )
