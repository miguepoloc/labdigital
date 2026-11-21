import sqlalchemy as sa
from sqlalchemy.orm import Session
import sqlalchemy.orm.exc

from backend.commerce.orders.adapters import orm
from backend.commerce.orders.domain.model import aggregate, exceptions, value_objects
from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects

_ACTIVE_STATUSES = (
    value_objects.OrderStatus.PENDING.value,
    value_objects.OrderStatus.CONFIRMED.value,
)


def _to_orm(order: aggregate.Order) -> orm.OrderOrm:
    return orm.OrderOrm(
        id=order.id.value,
        customer_id=order.customer_id.value,
        lines=[line.model_dump(mode="json") for line in order.lines],
        status=order.status.value,
        shipping_name=order.shipping_name,
        shipping_email=order.shipping_email,
        created_at=order.created_at.microseconds,
        updated_at=order.updated_at.microseconds,
        version=order.version,
    )


def _to_entity(order_orm: orm.OrderOrm) -> aggregate.Order:
    return aggregate.Order(
        id=value_objects.OrderId(value=order_orm.id),
        customer_id=value_objects.CustomerId(value=order_orm.customer_id),
        lines=[value_objects.OrderLine.model_validate(line) for line in order_orm.lines],
        status=value_objects.OrderStatus(order_orm.status),
        shipping_name=order_orm.shipping_name,
        shipping_email=order_orm.shipping_email,
        created_at=base_value_objects.PosixTime(microseconds=order_orm.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=order_orm.updated_at),
        version=order_orm.version,
    )


class DefaultOrderRepository(repositories.Repository[aggregate.Order]):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, id: value_objects.OrderId) -> aggregate.Order:  # noqa: A002
        order_orm = self._session.get(orm.OrderOrm, id.value)
        if order_orm is None:
            raise exceptions.OrderNotFoundError(order_id=id)
        return _to_entity(order_orm)

    def add(self, order: aggregate.Order) -> None:
        """`OrderId` is a `HumanFriendlyId` (ARCHITECTURE.md §5.2) — a real, if rare,
        primary-key collision is possible, so this goes through `insert_with_id_retry`
        rather than a plain `session.add()`. Syncs `order.id` back onto the aggregate if
        the id actually changed, so the caller's in-memory `order` and the persisted row
        never disagree."""
        row = _to_orm(order)
        final_id = repository_helpers.insert_with_id_retry(self._session, row)
        if final_id != order.id.value:
            order.id = value_objects.OrderId(value=final_id)
        repository_helpers.publish_events(self._session, order)

    def update(self, order: aggregate.Order) -> None:
        self._session.merge(_to_orm(order))
        try:
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                f"Order [{order.id}] changed concurrently — reload and retry.",
                code="CONCURRENT_MODIFICATION",
            ) from exc
        repository_helpers.publish_events(self._session, order)

    def delete(self, id: value_objects.OrderId) -> None:  # noqa: A002
        order_orm = self._session.get(orm.OrderOrm, id.value)
        if order_orm is not None:
            self._session.delete(order_orm)

    def list_active_for_customer(
        self, customer_id: value_objects.CustomerId
    ) -> list[aggregate.Order]:
        """Bespoke query — used by services/orders.py::cancel_pending_orders_for_customer
        (ARCHITECTURE.md §10.3's async UserDeactivated reaction). Lives on the concrete
        repository, not the generic Repository[T] interface (§7)."""
        stmt = sa.select(orm.OrderOrm).where(
            orm.OrderOrm.customer_id == customer_id.value,
            orm.OrderOrm.status.in_(_ACTIVE_STATUSES),
        )
        return [_to_entity(row) for row in self._session.execute(stmt).scalars()]

    def list_stale_pending_ids(
        self, *, created_before_microseconds: int
    ) -> list[value_objects.OrderId]:
        """Bespoke query — used by services/orders.py::expire_abandoned_orders
        (ARCHITECTURE.md §9.5/§18's cron entrypoint). IDs only, not full aggregates: the
        caller re-fetches (and re-checks status) one at a time inside its own transaction
        per order, so a batch that's partly stale by the time it runs doesn't corrupt
        anything — see the caller's docstring."""
        stmt = sa.select(orm.OrderOrm.id).where(
            orm.OrderOrm.status == value_objects.OrderStatus.PENDING.value,
            orm.OrderOrm.created_at < created_before_microseconds,
        )
        return [value_objects.OrderId(value=row) for row in self._session.execute(stmt).scalars()]


unit_of_work.register_repo(aggregate.Order, DefaultOrderRepository)
