"""Cursos con las piezas que no son de `courses`: nombre del docente (puerto
`UserDirectory`) y número de labs (`labs`). LD-4."""

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.teaching.commons import ports
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.domain.model import value_objects as courses_value_objects
from backend.teaching.courses.services import courses
from backend.teaching.courses.services import dto as courses_dto
from backend.teaching.labs.services import labs


def _complete(
    uow: unit_of_work.UnitOfWork,
    directory: ports.UserDirectory,
    items: list[courses_dto.CourseOutputDTO],
) -> list[courses_dto.CourseOutputDTO]:
    owners = directory.people([c.owner_id for c in items])
    completed = []
    for item in items:
        counts = item.counts
        if item.my_role == courses_value_objects.MembershipRole.DOCENTE.value or (
            item.my_role is None
        ):
            n_labs = len(labs.list_labs(uow=uow, course_id=item.id, published_only=False))
        else:
            n_labs = len(labs.list_labs(uow=uow, course_id=item.id, published_only=True))
        owner = owners.get(item.owner_id)
        completed.append(
            item.model_copy(
                update={
                    "owner_name": owner.full_name if owner else None,
                    "counts": counts.model_copy(update={"labs": n_labs}),
                }
            )
        )
    return completed


def list_my_courses(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
) -> list[courses_dto.CourseOutputDTO]:
    return _complete(uow, directory, courses.list_my_courses(uow=uow, viewer=viewer))


def get_course(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
    course_id: str,
) -> courses_dto.CourseOutputDTO:
    found = courses.get_course(uow=uow, viewer=viewer, course_id=course_id)
    return _complete(uow, directory, [found])[0]


def create_course(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    input_dto: courses_dto.CreateCourseInputDTO,
) -> courses_dto.CourseOutputDTO:
    created = courses.create_course(uow=uow, viewer=viewer, actor=actor, input_dto=input_dto)
    return _complete(uow, directory, [created])[0]


def update_course(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    course_id: str,
    input_dto: courses_dto.UpdateCourseInputDTO,
) -> courses_dto.CourseOutputDTO:
    updated = courses.update_course(
        uow=uow, viewer=viewer, actor=actor, course_id=course_id, input_dto=input_dto
    )
    return _complete(uow, directory, [updated])[0]


def rotate_join_code(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    course_id: str,
) -> courses_dto.CourseOutputDTO:
    rotated = courses.rotate_join_code(uow=uow, viewer=viewer, actor=actor, course_id=course_id)
    return _complete(uow, directory, [rotated])[0]


def join(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    code: str,
) -> courses_dto.CourseOutputDTO:
    joined = courses.join(uow=uow, viewer=viewer, actor=actor, code=code)
    return _complete(uow, directory, [joined])[0]


def list_members(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
    course_id: str,
    status: str | None,
) -> list[courses_dto.MembershipOutputDTO]:
    members = courses.list_members(uow=uow, viewer=viewer, course_id=course_id, status=status)
    found = directory.people([m.user_id for m in members])
    return [
        m.model_copy(
            update={
                "full_name": found[m.user_id].full_name if m.user_id in found else None,
                "email": found[m.user_id].email if m.user_id in found else None,
            }
        )
        for m in members
    ]


def decide_membership(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    course_id: str,
    user_id: str,
    decision: courses_value_objects.MembershipDecision,
) -> courses_dto.MembershipOutputDTO:
    decided = courses.decide_membership(
        uow=uow, viewer=viewer, actor=actor, course_id=course_id, user_id=user_id, decision=decision
    )
    person = directory.people([decided.user_id]).get(decided.user_id)
    return decided.model_copy(
        update={
            "full_name": person.full_name if person else None,
            "email": person.email if person else None,
        }
    )
