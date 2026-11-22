"""Construye un `FakeUnitOfWork` con todos los repositorios de `identity`."""

import dataclasses

from backend.identity.sessions.domain.model import aggregate as sessions_aggregate
from backend.identity.users.domain.model import aggregate as users_aggregate
from backend.identity.users.services import dto as users_dto
from tests import conftest
from tests.unit import fakes
from tests.unit.backend.identity.sessions import fakes as sessions_fakes
from tests.unit.backend.identity.users import fakes as users_fakes

CONFIG = users_dto.UsersConfig(
    public_base_url=conftest.PUBLIC_BASE_URL,
    admin_emails=frozenset({conftest.ADMIN_EMAIL}),
    data_policy_version="acuerdo-17-2018",
)
CONTEXT = users_dto.RequestContext(ip="10.0.0.1", user_agent="pytest")


@dataclasses.dataclass
class IdentityFakes:
    uow: fakes.FakeUnitOfWork
    users: users_fakes.FakeUserRepository
    tokens: users_fakes.FakeEmailTokenRepository
    sessions: sessions_fakes.FakeSessionRepository


def build() -> IdentityFakes:
    uow = fakes.FakeUnitOfWork()
    users = users_fakes.FakeUserRepository(uow.outbox)
    tokens = users_fakes.FakeEmailTokenRepository(uow.outbox)
    sessions = sessions_fakes.FakeSessionRepository(uow.outbox)
    uow.register(users_aggregate.User, users)
    uow.register(users_aggregate.EmailToken, tokens)
    uow.register(sessions_aggregate.Session, sessions)
    return IdentityFakes(uow=uow, users=users, tokens=tokens, sessions=sessions)
