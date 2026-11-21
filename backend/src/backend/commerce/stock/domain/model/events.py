from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.stock.domain.model import value_objects
from backend.commons.domain import events as domain_events


class StockCreated(domain_events.DomainEvent):
    stock_id: value_objects.StockId
    sku: commerce_value_objects.Sku


class StockReserved(domain_events.DomainEvent):
    stock_id: value_objects.StockId
    sku: commerce_value_objects.Sku
    quantity: int


class StockReleased(domain_events.DomainEvent):
    stock_id: value_objects.StockId
    sku: commerce_value_objects.Sku
    quantity: int
