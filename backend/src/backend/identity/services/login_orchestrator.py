"""Login = `users.authenticate` + `sessions.start_session` + access (ARCHITECTURE.md §10.2).

Sin transacción exterior a propósito: `authenticate` confirma por su cuenta el intento
(rate limit) y la auditoría de fallo antes de lanzar el error. Si `start_session` fallara
tras autenticar, el usuario simplemente reintenta (no queda estado a medias que importe).
"""

from backend.commons.adapters import unit_of_work
from backend.identity.services import _access_tokens, dto
from backend.identity.sessions.services import dto as sessions_dto
from backend.identity.sessions.services import sessions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users


def login(
    *,
    uow: unit_of_work.UnitOfWork,
    input_dto: dto.LoginInputDTO,
    context: users_dto.RequestContext,
) -> dto.LoginOutputDTO:
    authenticated = users.authenticate(
        uow=uow,
        input_dto=users_dto.LoginInputDTO(email=input_dto.email, password=input_dto.password),
        context=context,
    )
    issued = sessions.start_session(
        uow=uow,
        input_dto=sessions_dto.StartSessionInputDTO(
            user_id=authenticated.claims.user_id,
            credentials_version=authenticated.claims.credentials_version,
            persistent=input_dto.remember,
            ip=context.ip,
            user_agent=context.user_agent,
        ),
    )
    access = _access_tokens.issue(claims=authenticated.claims, session_id=issued.session_id)
    return dto.LoginOutputDTO(
        me=authenticated.me, tokens=dto.TokensOutputDTO(access_token=access, refresh=issued)
    )
