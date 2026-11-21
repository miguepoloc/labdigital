"""Refresh = rotar la familia (`sessions.rotate`, con detección de reuso) + releer los
claims del usuario (`users.get_token_claims`) + nuevo access.

Sin transacción exterior: un reuso debe confirmar la revocación antes de responder 401.
Si el usuario ya no está activo o sus credenciales cambiaron desde que se abrió la sesión,
se revoca la sesión y se responde 401 igualmente.
"""

from backend.commons.adapters import unit_of_work
from backend.identity.services import _access_tokens, dto
from backend.identity.sessions.domain.model import exceptions as sessions_exceptions
from backend.identity.sessions.domain.model import value_objects as sessions_value_objects
from backend.identity.sessions.services import sessions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users


def refresh(
    *,
    uow: unit_of_work.UnitOfWork,
    refresh_token: str,
    context: users_dto.RequestContext,
) -> dto.TokensOutputDTO:
    issued = sessions.rotate(
        uow=uow, refresh_token=refresh_token, ip=context.ip, user_agent=context.user_agent
    )
    claims = users.get_token_claims(uow=uow, user_id=issued.user_id)
    if not claims.is_active or claims.credentials_version != issued.credentials_version:
        reason = (
            sessions_value_objects.RevokeReason.USER_INACTIVE
            if not claims.is_active
            else sessions_value_objects.RevokeReason.CREDENTIALS_CHANGED
        )
        sessions.revoke_session(
            uow=uow, session_id=issued.session_id, owner_user_id=issued.user_id, reason=reason
        )
        raise sessions_exceptions.RefreshTokenInvalidError()
    access = _access_tokens.issue(claims=claims, session_id=issued.session_id)
    return dto.TokensOutputDTO(access_token=access, refresh=issued)
