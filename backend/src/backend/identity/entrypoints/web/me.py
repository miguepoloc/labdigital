"""`/v1/me` — contrato §4."""

import fastapi
from fastapi import status
import pydantic

from backend.commons.adapters.api import auth as api_auth
from backend.commons.application import dto as base_dto
from backend.identity.entrypoints.web import _dependencies
from backend.identity.services import change_password_orchestrator
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users

router = fastapi.APIRouter(prefix="/me", tags=["me"])


class UpdateMeBody(base_dto.BaseDTO):
    full_name: str = pydantic.Field(max_length=200)


class ChangePasswordBody(base_dto.BaseDTO):
    current: str = pydantic.Field(max_length=1024)
    new: str = pydantic.Field(max_length=1024)


@router.get("", response_model=users_dto.MeOutputDTO)
def get_me(claims: api_auth.ClaimsDep, uow: _dependencies.UowDep) -> users_dto.MeOutputDTO:
    return users.get_me(
        uow=uow, user_id=claims.user_id, credentials_version=claims.credentials_version
    )


@router.patch("", response_model=users_dto.MeOutputDTO)
def update_me(
    body: UpdateMeBody, claims: api_auth.ClaimsDep, uow: _dependencies.UowDep
) -> users_dto.MeOutputDTO:
    return users.update_me(
        uow=uow,
        user_id=claims.user_id,
        input_dto=users_dto.UpdateMeInputDTO(full_name=body.full_name),
    )


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordBody, claims: api_auth.ClaimsDep, uow: _dependencies.UowDep
) -> fastapi.Response:
    """Cierra las demás sesiones y re-emite la cookie de access de la actual."""
    result = change_password_orchestrator.change_password(
        uow=uow,
        user_id=claims.user_id,
        session_id=claims.session_id,
        input_dto=users_dto.ChangePasswordInputDTO(current=body.current, new=body.new),
    )
    response = fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)
    _dependencies.set_access_cookie(response, result.access_token)
    return response
