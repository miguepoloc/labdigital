import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class UserOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # Normalizado (minúsculas) por `value_objects.Email`; la unicidad es sobre este valor.
    email: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    role: Mapped[str] = mapped_column(sa.Text, nullable=False)
    email_verified_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    credentials_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    data_policy_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    data_policy_accepted_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}


class EmailTokenOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "email_tokens"
    __table_args__ = (sa.Index("ix_email_tokens_user_purpose", "user_id", "purpose"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(sa.Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    expires_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    used_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
