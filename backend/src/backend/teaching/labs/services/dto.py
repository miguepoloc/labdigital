import datetime
from typing import Any, Self

from backend.commons.application import dto
from backend.teaching.commons import dto as teaching_dto
from backend.teaching.labs.domain.model import aggregate


class LabInputDTO(dto.BaseDTO):
    """Crear (todos los campos) o editar (`PATCH`: sólo los que llegan, `fields_set`)."""

    title: str | None = None
    statement_md: str | None = None
    module: str | None = None
    opens_at: datetime.datetime | None = None
    due_at: datetime.datetime | None = None
    deadline_policy: str | None = None
    team_mode: str | None = None
    max_team_size: int | None = None
    grade_scale: dict[str, Any] | None = None
    allow_resubmission: bool | None = None


class LabOutputDTO(dto.BaseDTO):
    id: str
    course_id: str
    title: str
    statement_md: str
    module: str
    opens_at: str | None
    due_at: str | None
    deadline_policy: str
    team_mode: str
    max_team_size: int | None
    grade_scale: dict[str, Any]
    allow_resubmission: bool
    published: bool
    published_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, lab: aggregate.Lab) -> Self:
        return cls(
            id=str(lab.id),
            course_id=str(lab.course_id),
            title=lab.title.value,
            statement_md=lab.statement_md.value,
            module=lab.module.value,
            opens_at=teaching_dto.iso(lab.schedule.opens_at),
            due_at=teaching_dto.iso(lab.schedule.due_at),
            deadline_policy=lab.schedule.deadline_policy.value,
            team_mode=lab.team_setup.team_mode.value,
            max_team_size=lab.team_setup.max_team_size,
            grade_scale=lab.grade_scale.to_storage(),
            allow_resubmission=lab.allow_resubmission,
            published=lab.is_published,
            published_at=teaching_dto.iso(lab.published_at),
            created_at=teaching_dto.iso(lab.created_at) or "",
            updated_at=teaching_dto.iso(lab.updated_at) or "",
        )


class TeamMemberOutputDTO(dto.BaseDTO):
    user_id: str
    full_name: str | None = None


class TeamOutputDTO(dto.BaseDTO):
    """`join_code` sólo para integrantes y docente (los demás ven `null`)."""

    id: str
    lab_id: str
    name: str
    join_code: str | None
    locked: bool
    members: list[TeamMemberOutputDTO]
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, team: aggregate.Team) -> Self:
        return cls(
            id=str(team.id),
            lab_id=str(team.lab_id),
            name=team.name.value,
            join_code=team.join_code.value,
            locked=team.locked,
            members=[TeamMemberOutputDTO(user_id=str(m)) for m in team.members],
            created_at=teaching_dto.iso(team.created_at) or "",
            updated_at=teaching_dto.iso(team.updated_at) or "",
        )

    def member_ids(self) -> list[str]:
        return [m.user_id for m in self.members]


class SubmissionTimingOutputDTO(dto.BaseDTO):
    is_late: bool
