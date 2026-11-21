"""`/v1/labs/{id}/submissions` y `/v1/submissions/*` — contrato §4 "Entregas" y §6.1. LD-6."""

from typing import Any

import fastapi
from fastapi import status
import pydantic

from backend.commons.application import dto as base_dto
from backend.teaching.entrypoints.web import _dependencies as deps
from backend.teaching.services import dto, submissions_orchestrator

router = fastapi.APIRouter(tags=["submissions"])


class SubmitBody(base_dto.BaseDTO):
    project_id: str = pydantic.Field(max_length=64)
    version_id: str | None = pydantic.Field(default=None, max_length=64)
    file_ids: list[str] = pydantic.Field(default_factory=list, max_length=50)


class ReviewBody(base_dto.BaseDTO):
    grade: Any = None
    comment: str = pydantic.Field(default="", max_length=20_000)
    return_for_resubmission: bool = False


@router.post(
    "/labs/{lab_id}/submissions",
    response_model=dto.SubmissionOutputDTO,
    status_code=status.HTTP_201_CREATED,
)
def submit(
    lab_id: str,
    body: SubmitBody,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    projects_port: deps.ProjectsDep,
    files_port: deps.FilesDep,
    directory: deps.DirectoryDep,
) -> dto.SubmissionOutputDTO:
    return submissions_orchestrator.submit(
        uow=uow,
        viewer=viewer,
        actor=actor,
        projects_port=projects_port,
        files_port=files_port,
        directory=directory,
        lab_id=lab_id,
        input_dto=dto.SubmitInputDTO(**body.model_dump()),
    )


@router.get("/labs/{lab_id}/submissions", response_model=list[dto.SubmissionListItemOutputDTO])
def list_submissions(
    lab_id: str, viewer: deps.ViewerDep, uow: deps.UowDep, directory: deps.DirectoryDep
) -> list[dto.SubmissionListItemOutputDTO]:
    return submissions_orchestrator.list_for_lab(
        uow=uow, viewer=viewer, directory=directory, lab_id=lab_id
    )


@router.get("/submissions/{submission_id}", response_model=dto.SubmissionOutputDTO)
def get_submission(
    submission_id: str,
    viewer: deps.ViewerDep,
    uow: deps.UowDep,
    projects_port: deps.ProjectsDep,
    files_port: deps.FilesDep,
    directory: deps.DirectoryDep,
) -> dto.SubmissionOutputDTO:
    return submissions_orchestrator.get_submission(
        uow=uow,
        viewer=viewer,
        projects_port=projects_port,
        files_port=files_port,
        directory=directory,
        submission_id=submission_id,
    )


@router.post(
    "/submissions/{submission_id}/reviews",
    response_model=dto.SubmissionOutputDTO,
    status_code=status.HTTP_201_CREATED,
)
def review(
    submission_id: str,
    body: ReviewBody,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    projects_port: deps.ProjectsDep,
    files_port: deps.FilesDep,
    directory: deps.DirectoryDep,
) -> dto.SubmissionOutputDTO:
    """Devuelve la entrega con la revisión nueva. Nota fuera de escala ⇒ 422
    `details.fields.grade`."""
    return submissions_orchestrator.review(
        uow=uow,
        viewer=viewer,
        actor=actor,
        projects_port=projects_port,
        files_port=files_port,
        directory=directory,
        submission_id=submission_id,
        input_dto=dto.ReviewInputDTO(**body.model_dump()),
    )
