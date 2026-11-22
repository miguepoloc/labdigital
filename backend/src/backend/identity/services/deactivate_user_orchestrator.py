"""Desactivar usuario (lo usará el panel de admin): desactiva y revoca todas sus sesiones
en una transacción."""

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.identity.sessions.domain.model import value_objects as sessions_value_objects
from backend.identity.sessions.services import sessions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users


def deactivate_user(
    *, uow: unit_of_work.UnitOfWork, user_id: str, actor: audit.Actor
) -> users_dto.MeOutputDTO:
    with uow.transaction():
        me = users.deactivate_user(uow=uow, user_id=user_id, actor=actor)
        sessions.revoke_all_for_user(
            uow=uow, user_id=user_id, reason=sessions_value_objects.RevokeReason.USER_INACTIVE
        )
    return me
