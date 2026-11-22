"""`/v1/courses/{id}/labs`, `/v1/labs/*` y `/v1/teams/*` — contrato §4 "Labs"/"Equipos" y
§6.1 (`Lab`, `Team`). LD-5."""

import datetime
from typing import Any

import fastapi
from fastapi import status
import pydantic

from backend.commons.application import dto as base_dto
from backend.teaching.entrypoints.web import _dependencies as deps
from backend.teaching.labs.services import dto as labs_dto
from backend.teaching.services import dto, labs_orchestrator, teams_orchestrator

router = fastapi.APIRouter(tags=["labs"])


class LabBody(base_dto.BaseDTO):
    title: str | None = pydantic.Field(default=None, max_length=300)
    statement_md: str | None = None
    module: str | None = pydantic.Field(default=None, max_length=40)
    opens_at: datetime.datetime | None = None
    due_at: datetime.datetime | None = None
    deadline_policy: str | None = pydantic.Field(default=None, max_length=20)
    team_mode: str | None = pydantic.Field(default=None, max_length=20)
    max_team_size: int | None = None
    grade_scale: dict[str, Any] | None = None
    allow_resubmission: bool | None = None

    def to_input(self) -> labs_dto.LabInputDTO:
        sent = self.model_fields_set
        return labs_dto.LabInputDTO.model_validate({name: getattr(self, name) for name in sent})


class TeamBody(base_dto.BaseDTO):
    name: str = pydantic.Field(max_length=200)


class CodeBody(base_dto.BaseDTO):
    code: str = pydantic.Field(max_length=32)


@router.get("/courses/{course_id}/labs", response_model=list[dto.LabViewOutputDTO])
def list_labs(
    course_id: str, viewer: deps.ViewerDep, uow: deps.UowDep
) -> list[dto.LabViewOutputDTO]:
    return labs_orchestrator.list_labs(uow=uow, viewer=viewer, course_id=course_id)


@router.post(
    "/courses/{course_id}/labs",
    response_model=dto.LabViewOutputDTO,
    status_code=status.HTTP_201_CREATED,
)
def create_lab(
    course_id: str, body: LabBody, viewer: deps.ViewerDep, actor: deps.ActorDep, uow: deps.UowDep
) -> dto.LabViewOutputDTO:
    return labs_orchestrator.create_lab(
        uow=uow, viewer=viewer, actor=actor, course_id=course_id, input_dto=body.to_input()
    )


@router.get("/labs/{lab_id}", response_model=dto.LabViewOutputDTO)
def get_lab(lab_id: str, viewer: deps.ViewerDep, uow: deps.UowDep) -> dto.LabViewOutputDTO:
    return labs_orchestrator.get_lab(uow=uow, viewer=viewer, lab_id=lab_id)


@router.patch("/labs/{lab_id}", response_model=dto.LabViewOutputDTO)
def update_lab(
    lab_id: str, body: LabBody, viewer: deps.ViewerDep, actor: deps.ActorDep, uow: deps.UowDep
) -> dto.LabViewOutputDTO:
    return labs_orchestrator.update_lab(
        uow=uow, viewer=viewer, actor=actor, lab_id=lab_id, input_dto=body.to_input()
    )


@router.post("/labs/{lab_id}/publish", response_model=dto.LabViewOutputDTO)
def publish_lab(
    lab_id: str, viewer: deps.ViewerDep, actor: deps.ActorDep, uow: deps.UowDep
) -> dto.LabViewOutputDTO:
    return labs_orchestrator.publish_lab(uow=uow, viewer=viewer, actor=actor, lab_id=lab_id)


@router.get("/labs/{lab_id}/teams", response_model=list[dto.TeamViewOutputDTO])
def list_teams(
    lab_id: str, viewer: deps.ViewerDep, uow: deps.UowDep, directory: deps.DirectoryDep
) -> list[dto.TeamViewOutputDTO]:
    return teams_orchestrator.list_teams(uow=uow, viewer=viewer, directory=directory, lab_id=lab_id)


@router.post(
    "/labs/{lab_id}/teams",
    response_model=dto.TeamViewOutputDTO,
    status_code=status.HTTP_201_CREATED,
)
def create_team(
    lab_id: str,
    body: TeamBody,
    viewer: deps.ViewerDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> dto.TeamViewOutputDTO:
    """Devuelve el `Team` completo (incluye `join_code`, contrato §4)."""
    return teams_orchestrator.create_team(
        uow=uow, viewer=viewer, directory=directory, lab_id=lab_id, name=body.name
    )


@router.post("/labs/{lab_id}/teams/join", response_model=dto.TeamViewOutputDTO)
def join_team(
    lab_id: str,
    body: CodeBody,
    viewer: deps.ViewerDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> dto.TeamViewOutputDTO:
    return teams_orchestrator.join_team(
        uow=uow, viewer=viewer, directory=directory, lab_id=lab_id, code=body.code
    )


@router.post("/teams/{team_id}/leave", response_model=dto.TeamViewOutputDTO)
def leave_team(
    team_id: str, viewer: deps.ViewerDep, uow: deps.UowDep, directory: deps.DirectoryDep
) -> dto.TeamViewOutputDTO:
    return teams_orchestrator.leave_team(
        uow=uow, viewer=viewer, directory=directory, team_id=team_id
    )


@router.put("/teams/{team_id}/members", response_model=dto.TeamViewOutputDTO)
def set_team_members(
    team_id: str,
    member_ids: list[str],
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> dto.TeamViewOutputDTO:
    """Cuerpo: lista de ids de usuario (contrato §4 `PUT /teams/{id}/members [uid]`)."""
    return teams_orchestrator.set_members(
        uow=uow,
        viewer=viewer,
        actor=actor,
        directory=directory,
        team_id=team_id,
        member_ids=member_ids,
    )


@router.post("/teams/{team_id}/lock", response_model=dto.TeamViewOutputDTO)
def lock_team(
    team_id: str,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> dto.TeamViewOutputDTO:
    return teams_orchestrator.set_locked(
        uow=uow, viewer=viewer, actor=actor, directory=directory, team_id=team_id, locked=True
    )


@router.post("/teams/{team_id}/unlock", response_model=dto.TeamViewOutputDTO)
def unlock_team(
    team_id: str,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> dto.TeamViewOutputDTO:
    return teams_orchestrator.set_locked(
        uow=uow, viewer=viewer, actor=actor, directory=directory, team_id=team_id, locked=False
    )
