"""Limpieza periódica de `identity` (la lanza el worker cada hora)."""

from backend.commons.adapters import logs, unit_of_work
from backend.identity.sessions.services import sessions
from backend.identity.users.services import users

_LOGGER = logs.get_logger()


def run(uow: unit_of_work.UnitOfWork) -> None:
    expired_sessions = sessions.delete_expired(uow=uow)
    expired_tokens = users.delete_expired_email_tokens(uow=uow)
    _LOGGER.info(
        "Housekeeping identity: %s sesión(es) y %s token(s) de correo borrados",
        expired_sessions,
        expired_tokens,
    )
