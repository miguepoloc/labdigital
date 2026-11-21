import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, deferred, mapped_column

from backend.commons.adapters import orm_base


class ProjectOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "projects"
    __table_args__ = (
        sa.Index(
            "ix_projects_owner_module",
            "owner_id",
            "module",
            postgresql_where=sa.text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    module: Mapped[str] = mapped_column(sa.Text, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # FK diferida (ciclo projects ⇄ project_versions): se comprueba al confirmar.
    current_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey(
            "project_versions.id",
            name="fk_projects_current_version_id",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    )
    last_n: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # Contrato §6.1: sube en cada guardado de contenido.
    revision: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    deleted_at: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}


class ProjectVersionOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "project_versions"
    __table_args__ = (sa.UniqueConstraint("project_id", "n", name="uq_project_versions_project_n"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    n: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    label: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # `deferred`: listar versiones no carga hasta 2 MB por fila.
    content: Mapped[dict] = deferred(mapped_column(JSONB, nullable=False))
    size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # Entregada: el contenido ya no puede cambiar (trigger `project_versions_locked_guard`).
    locked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
