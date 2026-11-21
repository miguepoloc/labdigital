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


class CourseOutputDTO(dto.BaseDTO):
    """`Course`. `join_code` sólo para el docente/admin (`null` para estudiantes).
    `my_role`/`my_status`: relación del usuario con el curso (`null` si es admin ajeno)."""

    id: str
    name: str
    period: str
    description: str
    owner_id: str
    join_code: str | None
    archived_at: str | None
    created_at: str
    updated_at: str
    my_role: str | None
    my_status: str | None

    @classmethod
    def from_entity(
        cls,
        course: aggregate.Course,
        membership: aggregate.Membership | None,
        *,
        can_manage: bool,
    ) -> Self:
        return cls(
            id=str(course.id),
            name=course.name.value,
            period=course.period.value,
            description=course.description.value,
            owner_id=str(course.owner_id),
            join_code=course.join_code.display if can_manage else None,
            archived_at=teaching_dto.iso(course.archived_at),
            created_at=teaching_dto.iso(course.created_at) or "",
            updated_at=teaching_dto.iso(course.updated_at) or "",
            my_role=membership.role.value if membership else None,
            my_status=membership.status.value if membership else None,
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


class JoinOutputDTO(MembershipOutputDTO):
    course_name: str
    course_period: str
