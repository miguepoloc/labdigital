"""DTOs de los orquestadores de `teaching` (formas públicas del contrato §6.1)."""

from typing import Any

from backend.commons.application import dto
from backend.teaching.labs.services import dto as labs_dto
from backend.teaching.submissions.services import dto as submissions_dto


class PersonOutputDTO(dto.BaseDTO):
    id: str
    full_name: str


class LabViewOutputDTO(labs_dto.LabOutputDTO):
    """`Lab` = campos de creación + `id`, `course_id`, `published_at`, `my_submission`."""

    my_submission: submissions_dto.SubmissionSummaryDTO | None = None


class TeamViewOutputDTO(dto.BaseDTO):
    """`Team = {id, lab_id, name, locked, members: [{id, full_name}], join_code}`;
    `join_code` sólo para integrantes y docente."""

    id: str
    lab_id: str
    name: str
    locked: bool
    members: list[PersonOutputDTO]
    join_code: str | None
    created_at: str
    updated_at: str


class TeamRefOutputDTO(dto.BaseDTO):
    id: str
    name: str


class SubmissionFileOutputDTO(dto.BaseDTO):
    id: str
    kind: str
    name: str
    size: int
    mime: str


class ReviewOutputDTO(dto.BaseDTO):
    id: str
    reviewer_name: str
    grade: float | None
    comment: str
    returned_for_resubmission: bool
    created_at: str


class SubmissionListItemOutputDTO(submissions_dto.SubmissionSummaryDTO):
    """Listado: `SubmissionSummary` + quién y qué versión (sin `content`)."""

    lab_id: str
    project_id: str
    version_id: str
    version_n: int
    submitted_by: PersonOutputDTO
    team: TeamRefOutputDTO | None
    members: list[PersonOutputDTO]


class SubmissionOutputDTO(SubmissionListItemOutputDTO):
    """`Submission` (contrato §6.1): incluye `files`, `reviews` y `content` congelado."""

    files: list[SubmissionFileOutputDTO]
    reviews: list[ReviewOutputDTO]
    content: dict[str, Any]


class SubmitInputDTO(dto.BaseDTO):
    project_id: str
    version_id: str | None = None
    file_ids: list[str] = []


class ReviewInputDTO(dto.BaseDTO):
    grade: Any = None
    comment: str = ""
    return_for_resubmission: bool = False
