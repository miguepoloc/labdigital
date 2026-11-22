import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class SessionOrm(orm_base.Base, orm_base.TimestampsMixin):
    """Familia de refresh tokens (pantalla "Sesiones activas")."""

    __tablename__ = "sessions"
    __table_args__ = (sa.Index("ix_sessions_user_active", "user_id", "revoked_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    persistent: Mapped[bool] = mapped_column(nullable=False)
    user_agent: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    ip: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    credentials_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    last_used_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    current_token_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    revoked_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}


class RefreshTokenOrm(orm_base.Base):
    """Cada eslabón de la familia; los rotados se conservan para detectar reuso."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    rotated_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    revoked_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
