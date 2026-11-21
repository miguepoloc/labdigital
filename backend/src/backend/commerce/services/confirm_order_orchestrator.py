"""Product-level orchestrator — ARCHITECTURE.md §10.2. Calls other subcontexts' `services/`
functions only. Never imports `orders.domain.model.aggregate`/`adapters` or
`stock.domain.model.aggregate`/`adapters` — only `commerce.commons.value_objects` (typing +
reconstructing a VO from a DTO's plain field) and `orders.domain.model.ports` (typing the
`user_profile_port` parameter this function threads straight through to the caller-supplied
adapter — never imports `orders.adapters.user_profile_adapter` itself, see
enforcement-and-style.md §16's contract 6 exception, now covering `domain.model.ports` too)
and each subcontext's own `services`/`domain.model.value_objects`."""

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.orders.domain.model import ports as order_ports
from backend.commerce.orders.domain.model import value_objects as order_value_objects
from backend.commerce.orders.services import dto, orders
from backend.commerce.stock.domain.model import exceptions as stock_exceptions
from backend.commerce.stock.services import stock
from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import audit

_LOGGER = logs.get_logger()


def confirm_order(
    *,
    uow: unit_of_work.UnitOfWork,
    order_id: order_value_objects.OrderId,
    user_profile_port: order_ports.UserProfilePort,
    actor: audit.Actor,
) -> dto.OrderOutputDTO:
    """The profile fetch happens BEFORE `with uow.transaction():` opens — never inside it
    (ARCHITECTURE.md §8). A nested `uow.transaction()` call joins the outer one as a no-op
    (§8/§10.2), so calling the port from inside `orders.confirm_order` itself wouldn't have
    helped: the outer transaction here is what actually holds the DB connection open, so the
    I/O has to happen before this function opens it, not just before some inner call does."""
    order = orders.get_order(uow=uow, order_id=order_id)
    profile = user_profile_port.get_profile(order_value_objects.CustomerId(value=order.customer_id))

    with uow.transaction():
        for line in order.lines:
            sku = commerce_value_objects.Sku(value=line.sku)
            try:
                stock.reserve_stock(uow=uow, sku=sku, quantity=line.quantity, actor=actor)
            except stock_exceptions.InsufficientStockError as exc:
                # `stock.reserve_stock` already logged the full exception with sku/quantity
                # context (`_LOGGER.exception`, commerce/stock/services/stock.py) — this adds
                # the order_id correlation that log can't have, at `.warning` rather than
                # dumping the same traceback a second time.
                _LOGGER.warning("Could not confirm order [%s]: %s", order_id, exc)
                raise
        confirmed = orders.confirm_order(
            uow=uow,
            order_id=order_id,
            shipping_name=profile.full_name,
            shipping_email=profile.email,
            actor=actor,
        )
    _LOGGER.info(
        "Order [%s] confirmed with stock reserved for %s line(s)", order_id, len(order.lines)
    )
    return confirmed
