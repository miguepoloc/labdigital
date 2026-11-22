"""¿Sigue valiendo un access? (revisión de seguridad, punto 2). Sesión activa y del usuario
con la misma `ver`, y usuario activo con esa misma `ver`. Dos lecturas por PK."""

from backend.commons.adapters import unit_of_work
from backend.identity.sessions.services import sessions
from backend.identity.users.domain.model import exceptions as users_exceptions
from backend.identity.users.services import users


def is_live(
    *, uow: unit_of_work.UnitOfWork, user_id: str, session_id: str, credentials_version: int
) -> bool:
    with uow.transaction():
        if not sessions.is_live(
            uow=uow,
            session_id=session_id,
            user_id=user_id,
            credentials_version=credentials_version,
        ):
            return False
        try:
            claims = users.get_token_claims(uow=uow, user_id=user_id)
        except users_exceptions.UserNotFoundError:
            return False
    return claims.is_active and claims.credentials_version == credentials_version
