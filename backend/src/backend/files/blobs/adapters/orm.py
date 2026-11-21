import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class BlobOrm(orm_base.Base, orm_base.TimestampsMixin):
    """Archivo subido. El contenido está en `BLOB_DIR/<sha[0:2]>/<sha[2:4]>/<sha>`."""

    __tablename__ = "blobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha256: Mapped[str] = mapped_column(sa.Text, nullable=False, index=True)
    size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(sa.Text, nullable=False)
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
