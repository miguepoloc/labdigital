from backend.commerce.orders.domain.model import value_objects
from backend.commons.domain import events as domain_events


class OrderCreated(domain_events.DomainEvent):
    order_id: value_objects.OrderId
    customer_id: value_objects.CustomerId


class OrderConfirmed(domain_events.DomainEvent):
    order_id: value_objects.OrderId


class OrderCancelled(domain_events.DomainEvent):
    order_id: value_objects.OrderId
    lines: list[value_objects.OrderLine]
    previous_status: value_objects.OrderStatus
