from typing import Self

from backend.commons.application import dto
from backend.identity.users.domain.model import aggregate


class RegisterUserInputDTO(dto.BaseDTO):
    email: str
    full_name: str
    password: str


class LoginInputDTO(dto.BaseDTO):
    email: str
    password: str


class RefreshInputDTO(dto.BaseDTO):
    refresh_token: str


class DeactivateUserInputDTO(dto.BaseDTO):
    user_id: str


class TokenPairOutputDTO(dto.BaseDTO):
    access_token: str
    refresh_token: str


class UserOutputDTO(dto.BaseDTO):
    id: str
    email: str
    full_name: str
    is_active: bool

    @classmethod
    def from_entity(cls, user: aggregate.User) -> Self:
        return cls(
            id=str(user.id),
            email=user.email.value,
            full_name=user.full_name,
            is_active=user.is_active,
        )


class UserProfileOutputDTO(dto.BaseDTO):
    """Returned by entrypoints/web/internal.py — ARCHITECTURE.md §9.2. Deliberately a
    separate DTO from UserOutputDTO: this one is the public *inter-service* contract
    (§10.2b), so it stays intentionally narrow (only what orders needs to snapshot) rather
    than mirroring every field User happens to have."""

    user_id: str
    email: str
    full_name: str

    @classmethod
    def from_entity(cls, user: aggregate.User) -> Self:
        return cls(user_id=str(user.id), email=user.email.value, full_name=user.full_name)
