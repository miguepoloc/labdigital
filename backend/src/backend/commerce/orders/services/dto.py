from typing import Self

from backend.commerce.orders.domain.model import aggregate, value_objects
from backend.commons.application import dto
from backend.commons.domain import money


class OrderLineInputDTO(dto.BaseDTO):
    sku: str
    quantity: int


class CreateOrderInputDTO(dto.BaseDTO):
    customer_id: str
    lines: list[OrderLineInputDTO]


class OrderLineOutputDTO(dto.BaseDTO):
    sku: str
    quantity: int
    unit_price: str
    currency: money.Currencies


class OrderOutputDTO(dto.BaseDTO):
    id: str
    customer_id: str
    # A real enum, not `str` — the DTO boundary is where a bad status string would first be
    # caught (Pydantic rejects anything not in `OrderStatus` at construction time) instead of
    # silently flowing through as a magic string an `==` comparison downstream could typo.
    # StrEnum still serializes to the plain string value over the wire, so this changes
    # nothing about the JSON response.
    status: value_objects.OrderStatus
    lines: list[OrderLineOutputDTO]
    total: str
    currency: money.Currencies
    shipping_name: str | None
    shipping_email: str | None
    had_reserved_stock: bool

    @classmethod
    def from_entity(cls, order: aggregate.Order, *, had_reserved_stock: bool | None = None) -> Self:
        """`had_reserved_stock` is only ever passed explicitly by
        `services/orders.py::cancel_order`, which must capture it BEFORE calling
        `order.cancel()` — by the time this classmethod runs on a just-cancelled order,
        `order.had_reserved_stock` itself would already (incorrectly) read False. Every
        other caller lets it default to the property's live value."""
        total = order.total
        return cls(
            id=str(order.id),
            customer_id=str(order.customer_id.value),
            status=order.status,
            lines=[
                OrderLineOutputDTO(
                    sku=line.sku.value,
                    quantity=line.quantity,
                    unit_price=str(line.unit_price.value),
                    currency=line.unit_price.currency,
                )
                for line in order.lines
            ],
            total=str(total.value),
            currency=total.currency,
            shipping_name=order.shipping_name,
            shipping_email=order.shipping_email,
            had_reserved_stock=(
                order.had_reserved_stock if had_reserved_stock is None else had_reserved_stock
            ),
        )
