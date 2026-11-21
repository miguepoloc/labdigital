import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class StockOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "stock"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    available_quantity: Mapped[int] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}
