import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class CourseOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    period: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    join_code: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    archived_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}


class MembershipOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "course_memberships"
    __table_args__ = (
        sa.UniqueConstraint("course_id", "user_id", name="uq_course_memberships_course_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}
