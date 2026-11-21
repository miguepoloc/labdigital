"""`/v1/projects/*` — contrato §4 "Proyectos". Todas las rutas exigen `ld_access`."""

from typing import Annotated, Any

import fastapi
from fastapi import status
import pydantic

from backend.commons.adapters import unit_of_work
from backend.commons.adapters.api import auth as api_auth
from backend.commons.application import dto as base_dto
from backend.projects.projects.services import dto, projects

router = fastapi.APIRouter(prefix="/projects", tags=["projects"])


def get_uow() -> unit_of_work.UnitOfWork:
    return unit_of_work.build()


UowDep = Annotated[unit_of_work.UnitOfWork, fastapi.Depends(get_uow)]


class CreateProjectBody(base_dto.BaseDTO):
    name: str = pydantic.Field(max_length=200)
    module: str = pydantic.Field(max_length=40)
    content: dict[str, Any]


class RenameProjectBody(base_dto.BaseDTO):
    name: str = pydantic.Field(max_length=200)


class AutosaveBody(base_dto.BaseDTO):
    content: dict[str, Any]
    base_version: int
    base_revision: int | None = None


class ManualVersionBody(base_dto.BaseDTO):
    label: str | None = pydantic.Field(default=None, max_length=200)


@router.get("", response_model=list[dto.ProjectOutputDTO])
def list_projects(
    claims: api_auth.ClaimsDep, uow: UowDep, module: str | None = None
) -> list[dto.ProjectOutputDTO]:
    return projects.list_projects(uow=uow, owner_id=claims.user_id, module=module)


@router.post("", response_model=dto.ProjectDetailOutputDTO, status_code=status.HTTP_201_CREATED)
def create_project(
    body: CreateProjectBody, claims: api_auth.ClaimsDep, uow: UowDep
) -> dto.ProjectDetailOutputDTO:
    return projects.create_project(
        uow=uow,
        owner_id=claims.user_id,
        input_dto=dto.CreateProjectInputDTO(
            name=body.name, module=body.module, content=body.content
        ),
    )


@router.get("/{project_id}", response_model=dto.ProjectDetailOutputDTO)
def get_project(
    project_id: str, claims: api_auth.ClaimsDep, uow: UowDep
) -> dto.ProjectDetailOutputDTO:
    return projects.get_project(uow=uow, owner_id=claims.user_id, project_id=project_id)


@router.patch("/{project_id}", response_model=dto.ProjectOutputDTO)
def rename_project(
    project_id: str, body: RenameProjectBody, claims: api_auth.ClaimsDep, uow: UowDep
) -> dto.ProjectOutputDTO:
    return projects.rename_project(
        uow=uow, owner_id=claims.user_id, project_id=project_id, name=body.name
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, claims: api_auth.ClaimsDep, uow: UowDep) -> fastapi.Response:
    projects.delete_project(uow=uow, owner_id=claims.user_id, project_id=project_id)
    return fastapi.Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{project_id}/autosave", response_model=dto.AutosaveOutputDTO)
def autosave(
    project_id: str, body: AutosaveBody, claims: api_auth.ClaimsDep, uow: UowDep
) -> dto.AutosaveOutputDTO:
    return projects.autosave(
        uow=uow,
        owner_id=claims.user_id,
        project_id=project_id,
        input_dto=dto.AutosaveInputDTO(
            content=body.content,
            base_version=body.base_version,
            base_revision=body.base_revision,
        ),
    )


@router.post(
    "/{project_id}/versions",
    response_model=dto.VersionOutputDTO,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    project_id: str, claims: api_auth.ClaimsDep, uow: UowDep, body: ManualVersionBody | None = None
) -> dto.VersionOutputDTO:
    return projects.create_manual_version(
        uow=uow,
        owner_id=claims.user_id,
        project_id=project_id,
        label=body.label if body else None,
    )


@router.get("/{project_id}/versions", response_model=list[dto.VersionOutputDTO])
def list_versions(
    project_id: str, claims: api_auth.ClaimsDep, uow: UowDep
) -> list[dto.VersionOutputDTO]:
    return projects.list_versions(uow=uow, owner_id=claims.user_id, project_id=project_id)


@router.get("/{project_id}/versions/{version_id}", response_model=dto.VersionDetailOutputDTO)
def get_version(
    project_id: str, version_id: str, claims: api_auth.ClaimsDep, uow: UowDep
) -> dto.VersionDetailOutputDTO:
    return projects.get_version(
        uow=uow, owner_id=claims.user_id, project_id=project_id, version_id=version_id
    )


@router.post(
    "/{project_id}/versions/{version_id}/restore", response_model=dto.ProjectDetailOutputDTO
)
def restore_version(
    project_id: str, version_id: str, claims: api_auth.ClaimsDep, uow: UowDep
) -> dto.ProjectDetailOutputDTO:
    return projects.restore_version(
        uow=uow, owner_id=claims.user_id, project_id=project_id, version_id=version_id
    )
