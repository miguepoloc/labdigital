"""`Submission` con sus `Review` (LD-6).

Una entrega es de un estudiante (lab individual) o de un equipo (lab en equipo: cualquier
integrante entrega por todos). `member_ids` guarda quiénes eran del equipo AL ENTREGAR: es
lo que decide quién la ve y a quién se le pone la nota, aunque el equipo cambie después.

El proyecto se referencia por una versión CONGELADA (`FrozenProject`): `projects` la marcó
`locked`/`submitted` antes de crear esta entrega y ya no puede cambiar (ver
`projects.freeze_version`). La FK a `project_versions` es `RESTRICT`.
"""

from typing import Self

from backend.commons.domain import aggregates, entities
from backend.commons.domain import value_objects as base_value_objects
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.submissions.domain.model import events, exceptions, value_objects


class Review(entities.Entity[value_objects.ReviewId]):
    reviewer_id: teaching_value_objects.UserRef
    grade: teaching_value_objects.Grade | None
    comment: value_objects.Comment
    returned_for_resubmission: bool


class Submission(aggregates.AggregateRoot[value_objects.SubmissionId]):
    lab_id: teaching_value_objects.LabId
    course_id: teaching_value_objects.CourseId
    submitter_id: teaching_value_objects.UserRef
    student_id: teaching_value_objects.UserRef | None
    team_id: teaching_value_objects.TeamId | None
    member_ids: list[teaching_value_objects.UserRef]
    attempt: int
    project: value_objects.FrozenProject
    files: list[value_objects.SubmissionFile]
    is_late: bool
    status: value_objects.SubmissionStatus
    reviews: list[Review]

    @classmethod
    def submit(
        cls,
        *,
        lab_id: teaching_value_objects.LabId,
        course_id: teaching_value_objects.CourseId,
        submitter_id: teaching_value_objects.UserRef,
        team_id: teaching_value_objects.TeamId | None,
        member_ids: list[teaching_value_objects.UserRef],
        previous: "Submission | None",
        allow_resubmission: bool,
        project: value_objects.FrozenProject,
        files: list[value_objects.SubmissionFile],
        is_late: bool,
    ) -> Self:
        """Re-entrega sólo si el lab la permite o si el docente devolvió la anterior."""
        if previous is not None and not (
            allow_resubmission or previous.status is value_objects.SubmissionStatus.RETURNED
        ):
            raise exceptions.ResubmissionNotAllowedError()
        unique_files = list({f.blob_id: f for f in files}.values())
        if len(unique_files) > value_objects.MAX_FILES:
            raise exceptions.TooManyFilesError(value_objects.MAX_FILES)
        if sum(f.size for f in unique_files) > value_objects.MAX_SUBMISSION_BYTES:
            raise exceptions.SubmissionTooLargeError()
        now = base_value_objects.PosixTime.now()
        submission = cls(
            id=value_objects.SubmissionId.new(),
            lab_id=lab_id,
            course_id=course_id,
            submitter_id=submitter_id,
            student_id=None if team_id else submitter_id,
            team_id=team_id,
            member_ids=list(dict.fromkeys(member_ids or [submitter_id])),
            attempt=1 if previous is None else previous.attempt + 1,
            project=project,
            files=unique_files,
            is_late=is_late,
            status=value_objects.SubmissionStatus.SUBMITTED,
            reviews=[],
            created_at=now,
            updated_at=now,
        )
        submission.record_event(
            events.LabSubmitted(
                submission_id=submission.id,
                lab_id=lab_id,
                attempt=submission.attempt,
                is_late=is_late,
            )
        )
        return submission

    @property
    def owner_key(self) -> str:
        return f"team:{self.team_id}" if self.team_id else f"student:{self.student_id}"

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    def is_member(self, user_id: teaching_value_objects.UserRef) -> bool:
        return user_id in self.member_ids

    def latest_grade(self) -> teaching_value_objects.Grade | None:
        for review in reversed(self.reviews):
            if review.grade is not None:
                return review.grade
        return None

    def add_review(
        self,
        *,
        reviewer_id: teaching_value_objects.UserRef,
        grade: teaching_value_objects.Grade | None,
        comment: value_objects.Comment,
        return_for_resubmission: bool,
    ) -> Review:
        """Devolver ⇒ `returned` (admite re-entrega); con nota ⇒ `graded`; sólo comentario
        ⇒ el estado no cambia. La nota ya viene validada contra la escala del lab."""
        if grade is None and not comment.value and not return_for_resubmission:
            raise exceptions.EmptyReviewError()
        now = base_value_objects.PosixTime.now()
        review = Review(
            id=value_objects.ReviewId.new(),
            reviewer_id=reviewer_id,
            grade=grade,
            comment=comment,
            returned_for_resubmission=return_for_resubmission,
            created_at=now,
            updated_at=now,
        )
        self.reviews = [*self.reviews, review]
        if return_for_resubmission:
            self.status = value_objects.SubmissionStatus.RETURNED
        elif grade is not None:
            self.status = value_objects.SubmissionStatus.GRADED
        self.touch()
        self.record_event(events.SubmissionReviewed(submission_id=self.id, status=self.status))
        return review
