"""Panel de admin (`/admin/users`): exige rol admin EN BD; desactivar reutiliza el
orquestador existente (revoca todas las sesiones); cambiar el rol también revoca las
sesiones del usuario, para que ningún access con el rol viejo siga vivo más de 15 min
(el access en sí no se puede revocar: caduca solo). Todo queda en `audit_log`."""

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.identity.services import deactivate_user_orchestrator
from backend.identity.sessions.domain.model import value_objects as sessions_value_objects
from backend.identity.sessions.services import sessions
from backend.identity.users.domain.model import exceptions as users_exceptions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users


def search(
    *, uow: unit_of_work.UnitOfWork, admin_id: str, query: str | None, limit: int, offset: int
) -> list[users_dto.AdminUserOutputDTO]:
    users.require_admin(uow=uow, user_id=admin_id)
    return users.search_users(uow=uow, query=query, limit=limit, offset=offset)


def deactivate(
    *, uow: unit_of_work.UnitOfWork, admin_id: str, user_id: str, actor: audit.Actor
) -> users_dto.AdminUserOutputDTO:
    users.require_admin(uow=uow, user_id=admin_id)
    _not_self(admin_id, user_id)
    deactivate_user_orchestrator.deactivate_user(uow=uow, user_id=user_id, actor=actor)
    return users.get_admin_view(uow=uow, user_id=user_id)


def activate(
    *, uow: unit_of_work.UnitOfWork, admin_id: str, user_id: str, actor: audit.Actor
) -> users_dto.AdminUserOutputDTO:
    users.require_admin(uow=uow, user_id=admin_id)
    return users.activate_user(uow=uow, user_id=user_id, actor=actor)


def change_role(
    *, uow: unit_of_work.UnitOfWork, admin_id: str, user_id: str, role: str, actor: audit.Actor
) -> users_dto.AdminUserOutputDTO:
    users.require_admin(uow=uow, user_id=admin_id)
    _not_self(admin_id, user_id)
    with uow.transaction():
        before = users.get_admin_view(uow=uow, user_id=user_id)
        changed = users.change_role(uow=uow, user_id=user_id, role=role, actor=actor)
        if changed.role != before.role:
            sessions.revoke_all_for_user(
                uow=uow,
                user_id=user_id,
                reason=sessions_value_objects.RevokeReason.CREDENTIALS_CHANGED,
            )
    return changed


def _not_self(admin_id: str, user_id: str) -> None:
    if admin_id == user_id:
        raise users_exceptions.CannotModifySelfError()
