from typing import Self

from backend.commons.application import dto
from backend.teaching.commons import dto as teaching_dto
from backend.teaching.courses.domain.model import aggregate


class CreateCourseInputDTO(dto.BaseDTO):
    name: str
    period: str
    description: str = ""


class UpdateCourseInputDTO(dto.BaseDTO):
    name: str | None = None
    period: str | None = None
    description: str | None = None
    archived: bool | None = None


class CourseCountsDTO(dto.BaseDTO):
    students: int = 0
    pending: int = 0
    labs: int = 0


class CourseOutputDTO(dto.BaseDTO):
    """`Course` (contrato §6.1). `join_code` sólo si `my_role=docente`. `my_role`/`my_status`
    son `null` para un admin sin relación con el curso. `owner_name` y `counts.labs` los
    completa el orquestador (`teaching.services.courses_orchestrator`)."""

    id: str
    name: str
    period: str
    description: str
    archived_at: str | None
    owner_id: str
    owner_name: str | None = None
    my_role: str | None
    my_status: str | None
    join_code: str | None
    counts: CourseCountsDTO
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(
        cls,
        course: aggregate.Course,
        membership: aggregate.Membership | None,
        *,
        counts: CourseCountsDTO | None = None,
    ) -> Self:
        is_teacher = membership is not None and membership.is_teacher
        return cls(
            id=str(course.id),
            name=course.name.value,
            period=course.period.value,
            description=course.description.value,
            archived_at=teaching_dto.iso(course.archived_at),
            owner_id=str(course.owner_id),
            my_role=membership.role.value if membership else None,
            my_status=membership.status.value if membership else None,
            join_code=course.join_code.display if is_teacher else None,
            counts=counts or CourseCountsDTO(),
            created_at=teaching_dto.iso(course.created_at) or "",
            updated_at=teaching_dto.iso(course.updated_at) or "",
        )


class MembershipOutputDTO(dto.BaseDTO):
    """Membresía. `full_name`/`email` los rellena la capa que conoce a los usuarios
    (orquestador de nivel superior); aquí quedan vacíos."""

    course_id: str
    user_id: str
    role: str
    status: str
    requested_at: str
    updated_at: str
    full_name: str | None = None
    email: str | None = None

    @classmethod
    def from_entity(cls, membership: aggregate.Membership) -> Self:
        return cls(
            course_id=str(membership.course_id),
            user_id=str(membership.user_id),
            role=membership.role.value,
            status=membership.status.value,
            requested_at=teaching_dto.iso(membership.created_at) or "",
            updated_at=teaching_dto.iso(membership.updated_at) or "",
        )
