from typing import Self

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.stock.domain.model import events, exceptions, value_objects
from backend.commons.domain import aggregates
from backend.commons.domain import value_objects as base_value_objects


class Stock(aggregates.AggregateRoot[value_objects.StockId]):
    sku: commerce_value_objects.Sku
    available_quantity: int

    @classmethod
    def create(cls, *, sku: commerce_value_objects.Sku, initial_quantity: int) -> Self:
        now = base_value_objects.PosixTime.now()
        stock = cls(
            id=value_objects.StockId.new(),
            sku=sku,
            available_quantity=initial_quantity,
            created_at=now,
            updated_at=now,
        )
        stock.record_event(events.StockCreated(stock_id=stock.id, sku=sku))
        return stock

    def reserve(self, quantity: int) -> None:
        if self.available_quantity < quantity:
            raise exceptions.InsufficientStockError(
                sku=self.sku, requested=quantity, available=self.available_quantity
            )
        self.available_quantity -= quantity
        self.touch()
        self.record_event(events.StockReserved(stock_id=self.id, sku=self.sku, quantity=quantity))

    def release(self, quantity: int) -> None:
        self.available_quantity += quantity
        self.touch()
        self.record_event(events.StockReleased(stock_id=self.id, sku=self.sku, quantity=quantity))
