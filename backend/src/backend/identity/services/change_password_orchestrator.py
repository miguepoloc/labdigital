"""Cambio de contraseña con sesión abierta: exige la actual, sube `credentials_version`,
cierra las DEMÁS sesiones y re-emite el access de la actual (que sigue viva)."""

from backend.commons.adapters import unit_of_work
from backend.identity.services import _access_tokens, dto
from backend.identity.sessions.domain.model import value_objects as sessions_value_objects
from backend.identity.sessions.services import sessions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users


def change_password(
    *,
    uow: unit_of_work.UnitOfWork,
    user_id: str,
    session_id: str,
    input_dto: users_dto.ChangePasswordInputDTO,
) -> dto.ChangePasswordOutputDTO:
    with uow.transaction():
        sessions.ensure_active(uow=uow, session_id=session_id, user_id=user_id)
        claims = users.change_password(uow=uow, user_id=user_id, input_dto=input_dto)
        sessions.revoke_all_for_user(
            uow=uow,
            user_id=user_id,
            reason=sessions_value_objects.RevokeReason.PASSWORD_CHANGED,
            keep_session_id=session_id,
        )
        sessions.sync_credentials_version(
            uow=uow, session_id=session_id, credentials_version=claims.credentials_version
        )
    return dto.ChangePasswordOutputDTO(
        access_token=_access_tokens.issue(claims=claims, session_id=session_id)
    )
