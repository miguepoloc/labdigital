"""`/v1/admin/users` — contrato §4 "Admin". Sólo admins (comprobado en BD)."""

import fastapi
import pydantic

from backend.commons.adapters.api import auth as api_auth
from backend.commons.application import dto as base_dto
from backend.commons.domain import audit
from backend.identity.entrypoints.web import _dependencies
from backend.identity.services import admin_orchestrator
from backend.identity.users.services import dto as users_dto

router = fastapi.APIRouter(prefix="/admin", tags=["admin"])


class RoleBody(base_dto.BaseDTO):
    role: str = pydantic.Field(max_length=20)


def _actor(claims: api_auth.ClaimsDep) -> audit.Actor:
    return audit.Actor(id=claims.user_id, label=claims.email)


@router.get("/users", response_model=list[users_dto.AdminUserOutputDTO])
def list_users(
    claims: api_auth.ClaimsDep,
    uow: _dependencies.UowDep,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[users_dto.AdminUserOutputDTO]:
    return admin_orchestrator.search(
        uow=uow, admin_id=claims.user_id, query=q, limit=limit, offset=offset
    )


@router.post("/users/{user_id}/deactivate", response_model=users_dto.AdminUserOutputDTO)
def deactivate(
    user_id: str, claims: api_auth.ClaimsDep, uow: _dependencies.UowDep
) -> users_dto.AdminUserOutputDTO:
    return admin_orchestrator.deactivate(
        uow=uow, admin_id=claims.user_id, user_id=user_id, actor=_actor(claims)
    )


@router.post("/users/{user_id}/activate", response_model=users_dto.AdminUserOutputDTO)
def activate(
    user_id: str, claims: api_auth.ClaimsDep, uow: _dependencies.UowDep
) -> users_dto.AdminUserOutputDTO:
    return admin_orchestrator.activate(
        uow=uow, admin_id=claims.user_id, user_id=user_id, actor=_actor(claims)
    )


@router.post("/users/{user_id}/role", response_model=users_dto.AdminUserOutputDTO)
def change_role(
    user_id: str, body: RoleBody, claims: api_auth.ClaimsDep, uow: _dependencies.UowDep
) -> users_dto.AdminUserOutputDTO:
    return admin_orchestrator.change_role(
        uow=uow, admin_id=claims.user_id, user_id=user_id, role=body.role, actor=_actor(claims)
    )
