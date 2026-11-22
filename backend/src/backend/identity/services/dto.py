"""DTOs de los orquestadores de `identity` (nivel producto)."""

from backend.commons.application import dto
from backend.identity.sessions.services import dto as sessions_dto
from backend.identity.users.services import dto as users_dto


class LoginInputDTO(dto.BaseDTO):
    email: str
    password: str
    remember: bool = False


class TokensOutputDTO(dto.BaseDTO):
    """Par de tokens que la capa web convierte en cookies (`ld_access`/`ld_refresh`)."""

    access_token: str
    refresh: sessions_dto.IssuedRefreshOutputDTO


class LoginOutputDTO(dto.BaseDTO):
    me: users_dto.MeOutputDTO
    tokens: TokensOutputDTO


class ChangePasswordOutputDTO(dto.BaseDTO):
    access_token: str
