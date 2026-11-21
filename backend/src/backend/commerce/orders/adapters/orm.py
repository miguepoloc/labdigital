import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.commons.adapters import orm_base


class OrderOrm(orm_base.Base, orm_base.TimestampsMixin):
    __tablename__ = "orders"

    # str, not uuid.UUID — both OrderId and CustomerId are HumanFriendlyId (ARCHITECTURE.md
    # §5.2) — CustomerId because it mirrors identity.users.UserId's own value shape.
    id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(nullable=False, index=True)
    # OrderLine is a value object with no independent query needs of its own — embedded as
    # JSONB rather than a child table, a reasonable default until a real query against
    # individual lines is needed (see ARCHITECTURE.md §22.2's Middle Man caution: don't
    # build structure you don't have a use for yet).
    lines: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    shipping_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    shipping_email: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    version: Mapped[int] = mapped_column(default=0)

    __mapper_args__ = {"version_id_col": version}
