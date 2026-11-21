import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class LabOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "labs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    statement_md: Mapped[str] = mapped_column(sa.Text, nullable=False)
    module: Mapped[str] = mapped_column(sa.Text, nullable=False)
    opens_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    due_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    deadline_policy: Mapped[str] = mapped_column(sa.Text, nullable=False)
    team_mode: Mapped[str] = mapped_column(sa.Text, nullable=False)
    max_team_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    grade_scale: Mapped[dict] = mapped_column(JSONB, nullable=False)
    allow_resubmission: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    published_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}


class TeamOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "teams"
    __table_args__ = (sa.UniqueConstraint("lab_id", "join_code", name="uq_teams_lab_join_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    lab_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    join_code: Mapped[str] = mapped_column(sa.Text, nullable=False)
    locked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}


class TeamMemberOrm(orm_base.Base):
    """`(lab_id, user_id)` único: un estudiante está en un solo equipo por lab, lo
    garantiza Postgres aunque dos uniones lleguen a la vez."""

    __tablename__ = "team_members"
    __table_args__ = (sa.UniqueConstraint("lab_id", "user_id", name="uq_team_members_lab_user"),)

    team_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    lab_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("labs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
