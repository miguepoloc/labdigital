"""Capa de aplicación de `teaching.submissions` (LD-6). Como `labs`, no decide permisos:
la llama `teaching.services.submissions_orchestrator`, que ya comprobó curso, lab y equipo.
Excepción: `add_review` recibe la escala del lab y valida la nota (422 con
`details.fields.grade`)."""

import typing
import uuid

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import exceptions as commons_exceptions
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.submissions.adapters import repository
from backend.teaching.submissions.domain.model import aggregate, exceptions, value_objects
from backend.teaching.submissions.services import dto


def latest_for_owner(
    *, uow: unit_of_work.UnitOfWork, lab_id: str, student_id: str | None, team_id: str | None
) -> dto.SubmissionRecordDTO | None:
    key = f"team:{team_id}" if team_id else f"student:{student_id}"
    with uow.transaction():
        found = _repo(uow).latest_for_owner(_lab(lab_id), key)
    return None if found is None else dto.SubmissionRecordDTO.from_entity(found)


def create_submission(
    *, uow: unit_of_work.UnitOfWork, actor: audit.Actor, input_dto: dto.CreateSubmissionInputDTO
) -> dto.SubmissionRecordDTO:
    with uow.transaction():
        repo = _repo(uow)
        lab_id = _lab(input_dto.lab_id)
        team_id = (
            None
            if input_dto.team_id is None
            else teaching_value_objects.TeamId(value=uuid.UUID(input_dto.team_id))
        )
        submitter = _user(input_dto.submitter_id)
        owner_key = f"team:{team_id}" if team_id else f"student:{submitter}"
        previous = repo.latest_for_owner(lab_id, owner_key)
        submission = aggregate.Submission.submit(
            lab_id=lab_id,
            course_id=teaching_value_objects.CourseId(value=uuid.UUID(input_dto.course_id)),
            submitter_id=submitter,
            team_id=team_id,
            member_ids=[_user(m) for m in input_dto.member_ids],
            previous=previous,
            allow_resubmission=input_dto.allow_resubmission,
            project=value_objects.FrozenProject(
                project_id=uuid.UUID(input_dto.project.project_id),
                project_name=input_dto.project.project_name,
                version_id=uuid.UUID(input_dto.project.version_id),
                version_n=input_dto.project.version_n,
            ),
            files=[
                value_objects.SubmissionFile(
                    blob_id=uuid.UUID(f.blob_id),
                    kind=value_objects.FileKind(f.kind),
                    size=f.size,
                    name=f.name,
                )
                for f in input_dto.files
            ],
            is_late=input_dto.is_late,
        )
        repo.add(submission)
        uow.audit.add(
            _entry(
                submission,
                value_objects.AuditAction.SUBMITTED,
                actor,
                {
                    "lab_id": str(submission.lab_id),
                    "attempt": submission.attempt,
                    "is_late": submission.is_late,
                    "version_id": str(submission.project.version_id),
                },
            )
        )
    return dto.SubmissionRecordDTO.from_entity(submission)


def get_submission(*, uow: unit_of_work.UnitOfWork, submission_id: str) -> dto.SubmissionRecordDTO:
    with uow.transaction():
        found = _repo(uow).get(_submission_id(submission_id))
    return dto.SubmissionRecordDTO.from_entity(found)


def list_for_lab(
    *, uow: unit_of_work.UnitOfWork, lab_id: str, member_id: str | None
) -> list[dto.SubmissionRecordDTO]:
    """`member_id=None` ⇒ todas (docente); si no, sólo aquellas en las que está."""
    with uow.transaction():
        found = _repo(uow).list_for_lab(
            _lab(lab_id), member=None if member_id is None else _user(member_id)
        )
    return [dto.SubmissionRecordDTO.from_entity(s) for s in found]


def list_for_course(
    *, uow: unit_of_work.UnitOfWork, course_id: str, member_id: str | None = None
) -> list[dto.SubmissionRecordDTO]:
    with uow.transaction():
        found = _repo(uow).list_for_course(
            teaching_value_objects.CourseId(value=uuid.UUID(course_id)),
            member=None if member_id is None else _user(member_id),
        )
    return [dto.SubmissionRecordDTO.from_entity(s) for s in found]


def list_using_blob(*, uow: unit_of_work.UnitOfWork, blob_id: str) -> list[dto.SubmissionRecordDTO]:
    try:
        parsed = uuid.UUID(blob_id)
    except ValueError:
        return []
    with uow.transaction():
        found = _repo(uow).list_using_blob(parsed)
    return [dto.SubmissionRecordDTO.from_entity(s) for s in found]


def add_review(
    *,
    uow: unit_of_work.UnitOfWork,
    submission_id: str,
    reviewer_id: str,
    actor: audit.Actor,
    grade_scale: teaching_value_objects.GradeScale,
    grade: typing.Any,
    comment: str,
    return_for_resubmission: bool,
) -> dto.SubmissionRecordDTO:
    validated = None if grade is None else grade_scale.validate_grade(grade)
    with uow.transaction():
        repo = _repo(uow)
        submission = repo.get(_submission_id(submission_id))
        review = submission.add_review(
            reviewer_id=_user(reviewer_id),
            grade=validated,
            comment=value_objects.Comment(value=comment),
            return_for_resubmission=return_for_resubmission,
        )
        repo.update(submission)
        uow.audit.add(
            _entry(
                submission,
                value_objects.AuditAction.REVIEWED,
                actor,
                {
                    "review_id": str(review.id),
                    "grade": None if validated is None else validated.as_json(),
                    "returned_for_resubmission": return_for_resubmission,
                    "status": submission.status.value,
                },
            )
        )
    return dto.SubmissionRecordDTO.from_entity(submission)


def _entry(
    submission: aggregate.Submission,
    action: value_objects.AuditAction,
    actor: audit.Actor,
    changes: dict[str, typing.Any],
) -> audit.AuditEntry:
    return audit.AuditEntry(
        actor=actor,
        action=action.value,
        aggregate_type=value_objects.AuditAggregateType.SUBMISSION.value,
        aggregate_id=str(submission.id),
        changes=changes,
    )


def _lab(raw: str) -> teaching_value_objects.LabId:
    return teaching_value_objects.LabId(value=uuid.UUID(raw))


def _user(raw: str) -> teaching_value_objects.UserRef:
    parsed = teaching_value_objects.UserRef.parse(raw)
    if parsed is None:
        raise commons_exceptions.ValidationError(
            "Id de usuario no válido.", code="validation_error", details={"field": "user_id"}
        )
    return parsed


def _submission_id(raw: str) -> value_objects.SubmissionId:
    try:
        return value_objects.SubmissionId(value=uuid.UUID(raw))
    except ValueError as exc:
        raise exceptions.SubmissionNotFoundError() from exc


def _repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultSubmissionRepository:
    return typing.cast(repository.DefaultSubmissionRepository, uow.repo(aggregate.Submission))
