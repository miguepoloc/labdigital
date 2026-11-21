from typing import Self

from backend.commons.application import dto
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.users.domain.model import aggregate


def iso(value: base_value_objects.PosixTime) -> str:
    return value.to_datetime().isoformat().replace("+00:00", "Z")


class UsersConfig(dto.BaseDTO):
    """Configuración que el caso de uso necesita y que la entrypoint (raíz de composición)
    saca de `Settings` — así los servicios no leen el entorno y los tests la fijan."""

    public_base_url: str
    admin_emails: frozenset[str] = frozenset()
    data_policy_version: str


class RequestContext(dto.BaseDTO):
    """Datos de la petición que importan para auditoría y rate limiting."""

    ip: str
    user_agent: str = ""


class RegisterInputDTO(dto.BaseDTO):
    email: str
    full_name: str
    password: str
    accept_data_policy: bool


class LoginInputDTO(dto.BaseDTO):
    email: str
    password: str


class TokenInputDTO(dto.BaseDTO):
    token: str


class EmailInputDTO(dto.BaseDTO):
    email: str


class ResetPasswordInputDTO(dto.BaseDTO):
    token: str
    password: str


class UpdateMeInputDTO(dto.BaseDTO):
    full_name: str


class ChangePasswordInputDTO(dto.BaseDTO):
    current: str
    new: str


class MeOutputDTO(dto.BaseDTO):
    """`Me` del contrato §4."""

    id: str
    email: str
    full_name: str
    role: str
    email_verified: bool
    created_at: str

    @classmethod
    def from_entity(cls, user: aggregate.User) -> Self:
        return cls(
            id=str(user.id),
            email=user.email.value,
            full_name=user.full_name.value,
            role=user.role.value,
            email_verified=user.is_email_verified,
            created_at=iso(user.created_at),
        )


class TokenClaimsOutputDTO(dto.BaseDTO):
    """Lo que `sessions`/el orquestador necesitan para emitir un access."""

    user_id: str
    email: str
    full_name: str
    role: str
    credentials_version: int
    is_active: bool

    @classmethod
    def from_entity(cls, user: aggregate.User) -> Self:
        return cls(
            user_id=str(user.id),
            email=user.email.value,
            full_name=user.full_name.value,
            role=user.role.value,
            credentials_version=user.credentials_version,
            is_active=user.is_active,
        )


class AuthenticatedUserOutputDTO(dto.BaseDTO):
    me: MeOutputDTO
    claims: TokenClaimsOutputDTO
