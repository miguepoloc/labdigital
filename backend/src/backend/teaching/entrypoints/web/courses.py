"""`/v1/courses/*` — contrato §4 "Cursos" y §6.1 (`Course`). LD-4."""

from urllib import parse

import fastapi
from fastapi import status
import pydantic

from backend.commons.application import dto as base_dto
from backend.teaching.courses.domain.model import value_objects as courses_value_objects
from backend.teaching.courses.services import dto as courses_dto
from backend.teaching.entrypoints.web import _dependencies as deps
from backend.teaching.services import courses_orchestrator, grades_orchestrator

router = fastapi.APIRouter(prefix="/courses", tags=["courses"])


class CreateCourseBody(base_dto.BaseDTO):
    name: str = pydantic.Field(max_length=200)
    period: str = pydantic.Field(max_length=60)
    description: str = pydantic.Field(default="", max_length=5000)


class UpdateCourseBody(base_dto.BaseDTO):
    name: str | None = pydantic.Field(default=None, max_length=200)
    period: str | None = pydantic.Field(default=None, max_length=60)
    description: str | None = pydantic.Field(default=None, max_length=5000)
    archived: bool | None = None


class JoinBody(base_dto.BaseDTO):
    code: str = pydantic.Field(max_length=32)


@router.get("", response_model=list[courses_dto.CourseOutputDTO])
def list_courses(
    viewer: deps.ViewerDep, uow: deps.UowDep, directory: deps.DirectoryDep
) -> list[courses_dto.CourseOutputDTO]:
    return courses_orchestrator.list_my_courses(uow=uow, viewer=viewer, directory=directory)


@router.post("", response_model=courses_dto.CourseOutputDTO, status_code=status.HTTP_201_CREATED)
def create_course(
    body: CreateCourseBody,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> courses_dto.CourseOutputDTO:
    return courses_orchestrator.create_course(
        uow=uow,
        viewer=viewer,
        actor=actor,
        directory=directory,
        input_dto=courses_dto.CreateCourseInputDTO(**body.model_dump()),
    )


@router.post("/join", response_model=courses_dto.CourseOutputDTO)
def join_course(
    body: JoinBody,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> courses_dto.CourseOutputDTO:
    return courses_orchestrator.join(
        uow=uow, viewer=viewer, actor=actor, directory=directory, code=body.code
    )


@router.get("/{course_id}", response_model=courses_dto.CourseOutputDTO)
def get_course(
    course_id: str, viewer: deps.ViewerDep, uow: deps.UowDep, directory: deps.DirectoryDep
) -> courses_dto.CourseOutputDTO:
    return courses_orchestrator.get_course(
        uow=uow, viewer=viewer, directory=directory, course_id=course_id
    )


@router.patch("/{course_id}", response_model=courses_dto.CourseOutputDTO)
def update_course(
    course_id: str,
    body: UpdateCourseBody,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> courses_dto.CourseOutputDTO:
    return courses_orchestrator.update_course(
        uow=uow,
        viewer=viewer,
        actor=actor,
        directory=directory,
        course_id=course_id,
        input_dto=courses_dto.UpdateCourseInputDTO(**body.model_dump()),
    )


@router.post("/{course_id}/join-code/rotate", response_model=courses_dto.CourseOutputDTO)
def rotate_join_code(
    course_id: str,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> courses_dto.CourseOutputDTO:
    return courses_orchestrator.rotate_join_code(
        uow=uow, viewer=viewer, actor=actor, directory=directory, course_id=course_id
    )


@router.get("/{course_id}/members", response_model=list[courses_dto.MembershipOutputDTO])
def list_members(
    course_id: str,
    viewer: deps.ViewerDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
    status: str | None = None,
) -> list[courses_dto.MembershipOutputDTO]:
    return courses_orchestrator.list_members(
        uow=uow, viewer=viewer, directory=directory, course_id=course_id, status=status
    )


@router.post(
    "/{course_id}/members/{user_id}/{decision}", response_model=courses_dto.MembershipOutputDTO
)
def decide_membership(
    course_id: str,
    user_id: str,
    decision: courses_value_objects.MembershipDecision,
    viewer: deps.ViewerDep,
    actor: deps.ActorDep,
    uow: deps.UowDep,
    directory: deps.DirectoryDep,
) -> courses_dto.MembershipOutputDTO:
    """`decision` ∈ `approve|reject|remove`."""
    return courses_orchestrator.decide_membership(
        uow=uow,
        viewer=viewer,
        actor=actor,
        directory=directory,
        course_id=course_id,
        user_id=user_id,
        decision=decision,
    )


@router.get(
    "/{course_id}/grades.csv",
    response_class=fastapi.Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def grades_csv(
    course_id: str, viewer: deps.ViewerDep, uow: deps.UowDep, directory: deps.DirectoryDep
) -> fastapi.Response:
    """UTF-8 con BOM, `;`, coma decimal (Excel es-CO). Ver `grades_orchestrator`."""
    filename, content = grades_orchestrator.export_csv(
        uow=uow, viewer=viewer, directory=directory, course_id=course_id
    )
    return fastapi.Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{parse.quote(filename)}",
            "Cache-Control": "no-store",
        },
    )
