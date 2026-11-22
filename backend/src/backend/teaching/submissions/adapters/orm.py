import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class SubmissionOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "submissions"
    __table_args__ = (
        sa.UniqueConstraint("lab_id", "owner_key", "attempt", name="uq_submissions_attempt"),
        sa.CheckConstraint(
            "(student_id IS NULL) <> (team_id IS NULL)", name="ck_submissions_one_owner"
        ),
        sa.Index("ix_submissions_lab_owner", "lab_id", "owner_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    lab_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitter_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True
    )
    owner_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    attempt: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    project_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # RESTRICT: una versión entregada no se puede borrar mientras la entrega exista.
    project_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("project_versions.id", ondelete="RESTRICT"), nullable=False
    )
    project_version_n: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    is_late: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    total_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}


class SubmissionMemberOrm(orm_base.Base):
    """Quiénes eran del equipo al entregar (o el propio estudiante)."""

    __tablename__ = "submission_members"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class SubmissionFileOrm(orm_base.Base):
    __tablename__ = "submission_files"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True
    )
    blob_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("blobs.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class ReviewOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "submission_reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    grade_numeric: Mapped[float | None] = mapped_column(sa.Numeric(12, 2), nullable=True)
    grade_passed: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    comment: Mapped[str] = mapped_column(sa.Text, nullable=False)
    returned_for_resubmission: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
