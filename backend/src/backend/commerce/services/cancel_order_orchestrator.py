"""Product-level orchestrator — ARCHITECTURE.md §10.2. Only releases stock if the order had
actually reached CONFIRMED (i.e. had reserved stock via confirm_order_orchestrator) — a
still-PENDING order never reserved anything, so releasing anyway would inflate
available_quantity without ever having decremented it."""

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.orders.domain.model import value_objects as order_value_objects
from backend.commerce.orders.services import dto, orders
from backend.commerce.stock.services import stock
from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import audit

_LOGGER = logs.get_logger()


def cancel_order(
    *, uow: unit_of_work.UnitOfWork, order_id: order_value_objects.OrderId, actor: audit.Actor
) -> dto.OrderOutputDTO:
    with uow.transaction():
        # Tell, don't ask (ARCHITECTURE.md §22.3): this orchestrator asks
        # `cancelled_order.had_reserved_stock`, a named question `orders.cancel_order`
        # already answered by capturing it BEFORE mutating the order — it does not compare
        # a raw `.status` string against a magic value itself. A single call to
        # `orders.cancel_order` also replaces what used to be a separate `orders.get_order`
        # call just to peek at the pre-cancel status.
        cancelled_order = orders.cancel_order(uow=uow, order_id=order_id, actor=actor)

        if cancelled_order.had_reserved_stock:
            for line in cancelled_order.lines:
                sku = commerce_value_objects.Sku(value=line.sku)
                stock.release_stock(uow=uow, sku=sku, quantity=line.quantity, actor=actor)
            _LOGGER.info(
                "Order [%s] cancelled, stock released for %s line(s)",
                order_id,
                len(cancelled_order.lines),
            )

        return cancelled_order
