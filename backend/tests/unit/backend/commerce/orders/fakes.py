"""In-memory fake for `commerce.orders.adapters.repository.DefaultOrderRepository` —
ARCHITECTURE.md §15 / `shared-kernel-and-testing.md`'s `FakeStockRepository` example, applied
to `Order`. Extends the generic `Repository[T]` shape with the two bespoke queries
`DefaultOrderRepository` adds (`list_active_for_customer`, `list_stale_pending_ids`), and
drains `add`/`update` into the shared `FakeOutbox` the same way the real repository drains
into the real outbox (ARCHITECTURE.md §7/§11.2)."""

from backend.commerce.orders.domain.model import aggregate, exceptions, value_objects
from backend.commons.domain import repositories
from tests.unit import fakes

_ACTIVE_STATUSES = (value_objects.OrderStatus.PENDING, value_objects.OrderStatus.CONFIRMED)


class FakeOrderRepository(repositories.Repository[aggregate.Order]):
    def __init__(self, outbox: fakes.FakeOutbox) -> None:
        self._outbox = outbox
        self._by_id: dict[value_objects.OrderId, aggregate.Order] = {}

    def get(self, id: value_objects.OrderId) -> aggregate.Order:  # noqa: A002
        try:
            return self._by_id[id]
        except KeyError:
            raise exceptions.OrderNotFoundError(order_id=id) from None

    def add(self, order: aggregate.Order) -> None:
        self._by_id[order.id] = order
        fakes.drain_events(order, self._outbox)

    def update(self, order: aggregate.Order) -> None:
        self._by_id[order.id] = order
        fakes.drain_events(order, self._outbox)

    def delete(self, id: value_objects.OrderId) -> None:  # noqa: A002
        self._by_id.pop(id, None)

    def list_active_for_customer(
        self, customer_id: value_objects.CustomerId
    ) -> list[aggregate.Order]:
        return [
            order
            for order in self._by_id.values()
            if order.customer_id == customer_id and order.status in _ACTIVE_STATUSES
        ]

    def list_stale_pending_ids(
        self, *, created_before_microseconds: int
    ) -> list[value_objects.OrderId]:
        return [
            order.id
            for order in self._by_id.values()
            if order.status is value_objects.OrderStatus.PENDING
            and order.created_at.microseconds < created_before_microseconds
        ]
