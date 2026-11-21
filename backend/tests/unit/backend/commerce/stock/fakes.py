"""In-memory fake for `commerce.stock.adapters.repository.DefaultStockRepository` —
`shared-kernel-and-testing.md`'s own `FakeStockRepository` example, extended with `get`/
`delete` (the rest of `Repository[T]`'s contract) and event draining into the shared
`FakeOutbox`, matching what `DefaultStockRepository.add`/`.update` do internally
(ARCHITECTURE.md §7/§11.2/§15)."""

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.stock.domain.model import aggregate, exceptions, value_objects
from backend.commons.domain import repositories
from tests.unit import fakes


class FakeStockRepository(repositories.Repository[aggregate.Stock]):
    def __init__(self, outbox: fakes.FakeOutbox) -> None:
        self._outbox = outbox
        self._by_id: dict[value_objects.StockId, aggregate.Stock] = {}

    def get(self, id: value_objects.StockId) -> aggregate.Stock:  # noqa: A002
        try:
            return self._by_id[id]
        except KeyError:
            raise exceptions.StockNotFoundError(sku=id) from None

    def add(self, stock: aggregate.Stock) -> None:
        self._by_id[stock.id] = stock
        fakes.drain_events(stock, self._outbox)

    def update(self, stock: aggregate.Stock) -> None:
        self._by_id[stock.id] = stock
        fakes.drain_events(stock, self._outbox)

    def delete(self, id: value_objects.StockId) -> None:  # noqa: A002
        self._by_id.pop(id, None)

    def get_by_sku(self, sku: commerce_value_objects.Sku) -> aggregate.Stock:
        for stock in self._by_id.values():
            if stock.sku == sku:
                return stock
        raise exceptions.StockNotFoundError(sku=sku)
