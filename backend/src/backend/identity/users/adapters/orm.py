import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class UserOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "users"

    # str, not uuid.UUID — UserId is a HumanFriendlyId (ARCHITECTURE.md §5.2).
    id: Mapped[str] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    password_salt_hex: Mapped[str] = mapped_column(sa.Text, nullable=False)
    password_hash_hex: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}


class RefreshTokenOrm(orm_base.Base, orm_base.TimestampsMixin):
    """Persistence-only — not a domain aggregate (ARCHITECTURE.md §9.3). A refresh token
    carries no business invariant of its own beyond 'valid until revoked or expired,' so it
    doesn't earn the full Aggregate + Repository[T] machinery; identity/users/adapters
    /refresh_tokens.py manages this table directly."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    expires_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    revoked_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
