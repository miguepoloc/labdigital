import decimal
import uuid

import sqlalchemy as sa
from sqlalchemy import orm as sa_orm
import sqlalchemy.exc
import sqlalchemy.orm.exc

from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.submissions.adapters import orm
from backend.teaching.submissions.domain.model import aggregate, exceptions, value_objects


def _posix(value: int) -> base_value_objects.PosixTime:
    return base_value_objects.PosixTime(microseconds=value)


def _to_orm(s: aggregate.Submission) -> orm.SubmissionOrm:
    return orm.SubmissionOrm(
        id=s.id.value,
        lab_id=s.lab_id.value,
        course_id=s.course_id.value,
        submitter_id=s.submitter_id.value,
        student_id=None if s.student_id is None else s.student_id.value,
        team_id=None if s.team_id is None else s.team_id.value,
        owner_key=s.owner_key,
        attempt=s.attempt,
        project_id=s.project.project_id,
        project_name=s.project.project_name,
        project_version_id=s.project.version_id,
        project_version_n=s.project.version_n,
        is_late=s.is_late,
        status=s.status.value,
        total_bytes=s.total_bytes,
        created_at=s.created_at.microseconds,
        updated_at=s.updated_at.microseconds,
        version=s.version,
    )


def _review_to_entity(row: orm.ReviewOrm) -> aggregate.Review:
    grade = None
    if row.grade_numeric is not None:
        grade = teaching_value_objects.Grade(numeric=decimal.Decimal(str(row.grade_numeric)))
    elif row.grade_passed is not None:
        grade = teaching_value_objects.Grade(passed=row.grade_passed)
    return aggregate.Review(
        id=value_objects.ReviewId(value=row.id),
        reviewer_id=teaching_value_objects.UserRef(value=row.reviewer_id),
        grade=grade,
        comment=value_objects.Comment(value=row.comment),
        returned_for_resubmission=row.returned_for_resubmission,
        created_at=_posix(row.created_at),
        updated_at=_posix(row.updated_at),
    )


class DefaultSubmissionRepository(repositories.Repository[aggregate.Submission]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: value_objects.SubmissionId) -> aggregate.Submission:  # noqa: A002
        row = self._session.get(orm.SubmissionOrm, id.value)
        if row is None:
            raise exceptions.SubmissionNotFoundError()
        return self._load([row])[0]

    def latest_for_owner(
        self, lab_id: teaching_value_objects.LabId, owner_key: str
    ) -> aggregate.Submission | None:
        row = self._session.execute(
            sa.select(orm.SubmissionOrm)
            .where(
                orm.SubmissionOrm.lab_id == lab_id.value, orm.SubmissionOrm.owner_key == owner_key
            )
            .order_by(orm.SubmissionOrm.attempt.desc())
            .limit(1)
        ).scalar_one_or_none()
        return None if row is None else self._load([row])[0]

    def list_for_lab(
        self,
        lab_id: teaching_value_objects.LabId,
        *,
        member: teaching_value_objects.UserRef | None,
    ) -> list[aggregate.Submission]:
        stmt = sa.select(orm.SubmissionOrm).where(orm.SubmissionOrm.lab_id == lab_id.value)
        if member is not None:
            stmt = stmt.where(orm.SubmissionOrm.id.in_(self._member_subquery(member)))
        stmt = stmt.order_by(orm.SubmissionOrm.created_at.desc())
        return self._load(list(self._session.scalars(stmt)))

    def list_for_course(
        self,
        course_id: teaching_value_objects.CourseId,
        *,
        member: teaching_value_objects.UserRef | None = None,
    ) -> list[aggregate.Submission]:
        stmt = sa.select(orm.SubmissionOrm).where(orm.SubmissionOrm.course_id == course_id.value)
        if member is not None:
            stmt = stmt.where(orm.SubmissionOrm.id.in_(self._member_subquery(member)))
        stmt = stmt.order_by(orm.SubmissionOrm.created_at)
        return self._load(list(self._session.scalars(stmt)))

    def list_using_blob(self, blob_id: uuid.UUID) -> list[aggregate.Submission]:
        stmt = sa.select(orm.SubmissionOrm).where(
            orm.SubmissionOrm.id.in_(
                sa.select(orm.SubmissionFileOrm.submission_id).where(
                    orm.SubmissionFileOrm.blob_id == blob_id
                )
            )
        )
        return self._load(list(self._session.scalars(stmt)))

    def add(self, submission: aggregate.Submission) -> None:
        """Dos entregas simultáneas del mismo dueño chocan en `(lab, dueño, intento)`."""
        try:
            with self._session.begin_nested():
                self._session.add(_to_orm(submission))
                self._session.flush()
                for position, member in enumerate(submission.member_ids):
                    self._session.add(
                        orm.SubmissionMemberOrm(
                            submission_id=submission.id.value,
                            user_id=member.value,
                            position=position,
                        )
                    )
                for position, file in enumerate(submission.files):
                    self._session.add(
                        orm.SubmissionFileOrm(
                            submission_id=submission.id.value,
                            blob_id=file.blob_id,
                            kind=file.kind.value,
                            size=file.size,
                            name=file.name,
                            position=position,
                        )
                    )
                self._session.flush()
        except sqlalchemy.exc.IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_submissions_attempt":
                raise commons_exceptions.ConcurrentModificationError(
                    "Se registró otra entrega a la vez; recarga para ver el intento actual.",
                    code="concurrent_modification",
                ) from exc
            raise
        repository_helpers.publish_events(self._session, submission)

    def update(self, submission: aggregate.Submission) -> None:
        """Sólo cambian estado y revisiones (las revisiones son de sólo inserción)."""
        self._session.merge(_to_orm(submission))
        try:
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                "La entrega cambió a la vez; recarga e inténtalo de nuevo.",
                code="concurrent_modification",
            ) from exc
        existing = set(
            self._session.scalars(
                sa.select(orm.ReviewOrm.id).where(
                    orm.ReviewOrm.submission_id == submission.id.value
                )
            )
        )
        for review in submission.reviews:
            if review.id.value in existing:
                continue
            grade = review.grade
            self._session.add(
                orm.ReviewOrm(
                    id=review.id.value,
                    submission_id=submission.id.value,
                    reviewer_id=review.reviewer_id.value,
                    grade_numeric=None if grade is None else grade.numeric,
                    grade_passed=None if grade is None else grade.passed,
                    comment=review.comment.value,
                    returned_for_resubmission=review.returned_for_resubmission,
                    created_at=review.created_at.microseconds,
                    updated_at=review.updated_at.microseconds,
                )
            )
        self._session.flush()
        repository_helpers.publish_events(self._session, submission)

    def delete(self, id: value_objects.SubmissionId) -> None:  # noqa: A002
        row = self._session.get(orm.SubmissionOrm, id.value)
        if row is not None:
            self._session.delete(row)

    def _member_subquery(
        self, member: teaching_value_objects.UserRef
    ) -> sa.Select[tuple[uuid.UUID]]:
        return sa.select(orm.SubmissionMemberOrm.submission_id).where(
            orm.SubmissionMemberOrm.user_id == member.value
        )

    def _load(self, rows: list[orm.SubmissionOrm]) -> list[aggregate.Submission]:
        if not rows:
            return []
        ids = [r.id for r in rows]
        members: dict[uuid.UUID, list[teaching_value_objects.UserRef]] = {i: [] for i in ids}
        for m in self._session.scalars(
            sa.select(orm.SubmissionMemberOrm)
            .where(orm.SubmissionMemberOrm.submission_id.in_(ids))
            .order_by(orm.SubmissionMemberOrm.position)
        ):
            members[m.submission_id].append(teaching_value_objects.UserRef(value=m.user_id))
        files: dict[uuid.UUID, list[value_objects.SubmissionFile]] = {i: [] for i in ids}
        for f in self._session.scalars(
            sa.select(orm.SubmissionFileOrm)
            .where(orm.SubmissionFileOrm.submission_id.in_(ids))
            .order_by(orm.SubmissionFileOrm.position)
        ):
            files[f.submission_id].append(
                value_objects.SubmissionFile(
                    blob_id=f.blob_id, kind=value_objects.FileKind(f.kind), size=f.size, name=f.name
                )
            )
        reviews: dict[uuid.UUID, list[aggregate.Review]] = {i: [] for i in ids}
        for r in self._session.scalars(
            sa.select(orm.ReviewOrm)
            .where(orm.ReviewOrm.submission_id.in_(ids))
            .order_by(orm.ReviewOrm.created_at, orm.ReviewOrm.id)
        ):
            reviews[r.submission_id].append(_review_to_entity(r))
        return [
            aggregate.Submission(
                id=value_objects.SubmissionId(value=row.id),
                lab_id=teaching_value_objects.LabId(value=row.lab_id),
                course_id=teaching_value_objects.CourseId(value=row.course_id),
                submitter_id=teaching_value_objects.UserRef(value=row.submitter_id),
                student_id=None
                if row.student_id is None
                else teaching_value_objects.UserRef(value=row.student_id),
                team_id=None
                if row.team_id is None
                else teaching_value_objects.TeamId(value=row.team_id),
                member_ids=members[row.id],
                attempt=row.attempt,
                project=value_objects.FrozenProject(
                    project_id=row.project_id,
                    project_name=row.project_name,
                    version_id=row.project_version_id,
                    version_n=row.project_version_n,
                ),
                files=files[row.id],
                is_late=row.is_late,
                status=value_objects.SubmissionStatus(row.status),
                reviews=reviews[row.id],
                created_at=_posix(row.created_at),
                updated_at=_posix(row.updated_at),
                version=row.version,
            )
            for row in rows
        ]


unit_of_work.register_repo(aggregate.Submission, DefaultSubmissionRepository)
