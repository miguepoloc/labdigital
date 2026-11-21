"""Restablecer contraseña: cambia la contraseña (sube `credentials_version`) y revoca TODAS
las sesiones del usuario, en una sola transacción (ARCHITECTURE.md §8/§10.2)."""

from backend.commons.adapters import unit_of_work
from backend.identity.sessions.domain.model import value_objects as sessions_value_objects
from backend.identity.sessions.services import sessions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users


def reset_password(
    *,
    uow: unit_of_work.UnitOfWork,
    input_dto: users_dto.ResetPasswordInputDTO,
    config: users_dto.UsersConfig,
) -> None:
    with uow.transaction():
        claims = users.reset_password(uow=uow, input_dto=input_dto, config=config)
        sessions.revoke_all_for_user(
            uow=uow,
            user_id=claims.user_id,
            reason=sessions_value_objects.RevokeReason.PASSWORD_RESET,
        )
