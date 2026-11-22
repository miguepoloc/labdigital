"""DTOs compartidos por los subcontextos de `teaching`."""

from backend.commons.application import dto
from backend.commons.domain import value_objects as base_value_objects


def iso(value: base_value_objects.PosixTime | None) -> str | None:
    if value is None:
        return None
    return value.to_datetime().isoformat().replace("+00:00", "Z")


class CourseAccessDTO(dto.BaseDTO):
    """Relación del que mira con un curso, para que los orquestadores decidan permisos.

    `can_manage`: docente del curso o admin. `is_active_student`: estudiante aprobado."""

    course_id: str
    owner_id: str
    can_manage: bool
    is_active_student: bool
    archived: bool
