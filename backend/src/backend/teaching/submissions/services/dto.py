from typing import Self

from backend.commons.application import dto
from backend.teaching.commons import dto as teaching_dto
from backend.teaching.submissions.domain.model import aggregate


class FileRefInputDTO(dto.BaseDTO):
    blob_id: str
    kind: str
    size: int
    name: str


class FrozenProjectInputDTO(dto.BaseDTO):
    project_id: str
    project_name: str
    version_id: str
    version_n: int


class CreateSubmissionInputDTO(dto.BaseDTO):
    lab_id: str
    course_id: str
    submitter_id: str
    team_id: str | None
    member_ids: list[str]
    allow_resubmission: bool
    is_late: bool
    project: FrozenProjectInputDTO
    files: list[FileRefInputDTO]


class ReviewRecordDTO(dto.BaseDTO):
    id: str
    reviewer_id: str
    grade: float | None
    comment: str
    returned_for_resubmission: bool
    created_at: str


class FileRecordDTO(dto.BaseDTO):
    blob_id: str
    kind: str
    size: int
    name: str


class SubmissionRecordDTO(dto.BaseDTO):
    """Entrega con ids (los nombres los añade quien conoce a los usuarios)."""

    id: str
    lab_id: str
    course_id: str
    attempt: int
    status: str
    is_late: bool
    submitted_at: str
    grade: float | None
    submitter_id: str
    team_id: str | None
    member_ids: list[str]
    project_id: str
    project_name: str
    version_id: str
    version_n: int
    files: list[FileRecordDTO]
    reviews: list[ReviewRecordDTO]

    @classmethod
    def from_entity(cls, s: aggregate.Submission) -> Self:
        grade = s.latest_grade()
        return cls(
            id=str(s.id),
            lab_id=str(s.lab_id),
            course_id=str(s.course_id),
            attempt=s.attempt,
            status=s.status.value,
            is_late=s.is_late,
            submitted_at=teaching_dto.iso(s.created_at) or "",
            grade=None if grade is None else grade.as_json(),
            submitter_id=str(s.submitter_id),
            team_id=None if s.team_id is None else str(s.team_id),
            member_ids=[str(m) for m in s.member_ids],
            project_id=str(s.project.project_id),
            project_name=s.project.project_name,
            version_id=str(s.project.version_id),
            version_n=s.project.version_n,
            files=[
                FileRecordDTO(blob_id=str(f.blob_id), kind=f.kind.value, size=f.size, name=f.name)
                for f in s.files
            ],
            reviews=[
                ReviewRecordDTO(
                    id=str(r.id),
                    reviewer_id=str(r.reviewer_id),
                    grade=None if r.grade is None else r.grade.as_json(),
                    comment=r.comment.value,
                    returned_for_resubmission=r.returned_for_resubmission,
                    created_at=teaching_dto.iso(r.created_at) or "",
                )
                for r in s.reviews
            ],
        )


class SubmissionSummaryDTO(dto.BaseDTO):
    """`SubmissionSummary` del contrato §6.1."""

    id: str
    attempt: int
    status: str
    is_late: bool
    submitted_at: str
    grade: float | None

    @classmethod
    def from_record(cls, record: SubmissionRecordDTO) -> Self:
        return cls(
            id=record.id,
            attempt=record.attempt,
            status=record.status,
            is_late=record.is_late,
            submitted_at=record.submitted_at,
            grade=record.grade,
        )
