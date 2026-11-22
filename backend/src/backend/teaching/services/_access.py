"""Comprobaciones de permisos compartidas por los orquestadores de `teaching`."""

from backend.commons.adapters import unit_of_work
from backend.teaching.commons import dto as teaching_dto
from backend.teaching.commons import ports
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.domain.model import exceptions as courses_exceptions
from backend.teaching.courses.services import courses
from backend.teaching.labs.domain.model import exceptions as labs_exceptions
from backend.teaching.labs.services import dto as labs_dto
from backend.teaching.labs.services import labs
from backend.teaching.services import dto


def course(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, course_id: str
) -> teaching_dto.CourseAccessDTO:
    """404 si no hay relación visible con el curso."""
    return courses.get_access(uow=uow, viewer=viewer, course_id=course_id)


def require_manage(access: teaching_dto.CourseAccessDTO) -> None:
    if not access.can_manage:
        raise courses_exceptions.NotCourseTeacherError()


def require_active_student(access: teaching_dto.CourseAccessDTO) -> None:
    if not access.is_active_student:
        raise courses_exceptions.NotActiveStudentError()


def require_open(access: teaching_dto.CourseAccessDTO) -> None:
    if access.archived:
        raise courses_exceptions.CourseArchivedError()


def lab(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, lab_id: str
) -> tuple[labs_dto.LabOutputDTO, teaching_dto.CourseAccessDTO]:
    """El lab y la relación con su curso. Sin relación ⇒ 404; estudiante (o pendiente)
    y lab sin publicar ⇒ 404 (invisible)."""
    found = labs.get_lab(uow=uow, lab_id=lab_id)
    try:
        access = course(uow, viewer, found.course_id)
    except courses_exceptions.CourseNotFoundError as exc:
        raise labs_exceptions.LabNotFoundError() from exc
    if not access.can_manage and not found.published:
        raise labs_exceptions.LabNotFoundError()
    return found, access


def people(directory: ports.UserDirectory, ids: list[str]) -> dict[str, dto.PersonOutputDTO]:
    found = directory.people(list(dict.fromkeys(ids)))
    return {
        i: dto.PersonOutputDTO(id=i, full_name=found[i].full_name if i in found else "")
        for i in ids
    }
