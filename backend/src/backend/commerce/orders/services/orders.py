"""Application layer for commerce/orders — ARCHITECTURE.md §6. The only module allowed to
call `uow.repo(aggregate.Order)` or an Order command method.

Deliberately does NOT import `adapters/pricing_adapter.py` or `adapters/user_profile_adapter.py`
— the concrete adapter is constructed at the composition root (the FastAPI entrypoint, or the
orchestrator for the confirm flow, ARCHITECTURE.md §10.2) and threaded in as a required
keyword argument, matching bold's `_get_breb_cashin_pricing_adapter()` pattern: a service
function never falls back to `port or DefaultAdapter()` — that DI decision belongs to
whoever is wiring the call, not to the business logic being called.

Also deliberately does NOT call `uow.outbox.record(...)` anywhere — `DefaultOrderRepository
.add`/`.update` do that internally now (ARCHITECTURE.md §7/§11.2), so there is no
`_publish_events()` helper here to remember to call."""

import typing

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.orders.adapters import repository
from backend.commerce.orders.domain.model import aggregate, ports, value_objects
from backend.commerce.orders.services import dto
from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import value_objects as base_value_objects

_LOGGER = logs.get_logger()

_SYSTEM_EXPIRE_ACTOR = audit.Actor(id=None, label="system:expire_pending_orders_cron")


def create_order(
    *,
    uow: unit_of_work.UnitOfWork,
    input_dto: dto.CreateOrderInputDTO,
    pricing_port: ports.PricingPort,
    actor: audit.Actor,
) -> dto.OrderOutputDTO:
    """Single-aggregate use case (ARCHITECTURE.md §10.1) — no orchestrator. The external
    price lookup happens BEFORE the transaction opens, never inside it (holding a DB
    transaction open across network I/O is its own anti-pattern, §9.4's escape-hatch
    reasoning applied here too)."""
    lines = [
        value_objects.OrderLine(
            sku=(sku := commerce_value_objects.Sku(value=line.sku)),
            quantity=line.quantity,
            unit_price=pricing_port.get_unit_price(sku),
        )
        for line in input_dto.lines
    ]

    with uow.transaction():
        order = aggregate.Order.create(
            customer_id=value_objects.CustomerId(value=input_dto.customer_id),
            lines=lines,
        )
        _order_repo(uow).add(order)
        uow.audit.add(
            audit.AuditEntry(
                actor=actor,
                action=value_objects.AuditAction.CREATED,
                aggregate_type=value_objects.AuditAggregateType.ORDER,
                aggregate_id=order.id.value,
            )
        )
    _LOGGER.info("Order [%s] created for customer [%s]", order.id, order.customer_id)
    return dto.OrderOutputDTO.from_entity(order)


def get_order(
    *, uow: unit_of_work.UnitOfWork, order_id: value_objects.OrderId
) -> dto.OrderOutputDTO:
    with uow.transaction():
        order = uow.repo(aggregate.Order).get(order_id)
    return dto.OrderOutputDTO.from_entity(order)


def confirm_order(
    *,
    uow: unit_of_work.UnitOfWork,
    order_id: value_objects.OrderId,
    shipping_name: str,
    shipping_email: str,
    actor: audit.Actor,
) -> dto.OrderOutputDTO:
    """Takes the shipping snapshot as plain data, not a `UserProfilePort` — the caller
    (services/confirm_order_orchestrator.py) fetches it via the port BEFORE opening any
    transaction, so this function's own `with uow.transaction():` never has to hold a DB
    transaction open across the network call (ARCHITECTURE.md §8's no-I/O-inside-an-open-
    transaction rule; §10.2b explains why the fetch belongs to the orchestrator here, not
    to this single-aggregate service)."""
    with uow.transaction():
        order_repo = _order_repo(uow)  # uow.repo(...) needs a session, so this must be
        # inside the transaction() block, not before it — calling it earlier raises
        # RuntimeError (UnitOfWork.session is only set once a transaction is open).
        order = order_repo.get(order_id)
        order.confirm(shipping_name=shipping_name, shipping_email=shipping_email)
        order_repo.update(order)
        uow.audit.add(
            audit.AuditEntry(
                actor=actor,
                action=value_objects.AuditAction.CONFIRMED,
                aggregate_type=value_objects.AuditAggregateType.ORDER,
                aggregate_id=order.id.value,
            )
        )
    _LOGGER.info("Order [%s] confirmed", order.id)
    return dto.OrderOutputDTO.from_entity(order)


def cancel_order(
    *, uow: unit_of_work.UnitOfWork, order_id: value_objects.OrderId, actor: audit.Actor
) -> dto.OrderOutputDTO:
    with uow.transaction():
        order_repo = _order_repo(uow)
        order = order_repo.get(order_id)
        had_reserved_stock = order.had_reserved_stock  # ask BEFORE telling it to cancel —
        # cancel() flips self.status to CANCELLED, after which the property would (wrongly)
        # read False (ARCHITECTURE.md §5.3's Tell-Don't-Ask note on this exact property).
        order.cancel()  # raises OrderCannotBeCancelledError → rollback
        order_repo.update(order)
        uow.audit.add(
            audit.AuditEntry(
                actor=actor,
                action=value_objects.AuditAction.CANCELLED,
                aggregate_type=value_objects.AuditAggregateType.ORDER,
                aggregate_id=order.id.value,
            )
        )
    _LOGGER.info("Order [%s] cancelled", order.id)
    return dto.OrderOutputDTO.from_entity(order, had_reserved_stock=had_reserved_stock)


def cancel_pending_orders_for_customer(
    *, uow: unit_of_work.UnitOfWork, customer_id: value_objects.CustomerId
) -> int:
    """Called from commerce/entrypoints/events/on_user_deactivated.py (ARCHITECTURE.md
    §9.4/§10.3) — the async reaction to identity's UserDeactivated event. Every order this
    reacts to is, by construction, PENDING or CONFIRMED (`list_active_for_customer`'s own
    filter) — cancelling never needs `had_reserved_stock` here because nothing downstream
    releases stock for this path; a deactivated customer's confirmed orders staying
    reserved-but-cancelled is a deliberate simplification, not an oversight (see the
    template's README)."""
    # actor.id traces back to the user whose deactivation triggered this — CustomerId
    # mirrors UserId's value shape (see value_objects.py) — but actor.label still says
    # "system": the customer didn't cancel this order themselves, the async reaction to
    # their deactivation did.
    actor = audit.Actor(id=customer_id.value, label="system:on_user_deactivated")
    cancelled = 0
    with uow.transaction():
        order_repo = _order_repo(uow)
        for order in order_repo.list_active_for_customer(customer_id):
            order.cancel()
            order_repo.update(order)
            uow.audit.add(
                audit.AuditEntry(
                    actor=actor,
                    action=value_objects.AuditAction.CANCELLED,
                    aggregate_type=value_objects.AuditAggregateType.ORDER,
                    aggregate_id=order.id.value,
                )
            )
            cancelled += 1
    return cancelled


def expire_abandoned_orders(
    *, uow: unit_of_work.UnitOfWork, abandoned_after_microseconds: int
) -> int:
    """Called only from entrypoints/cron/expire_pending_orders.py. A PENDING order never
    reserved stock (only a CONFIRMED one does, ARCHITECTURE.md §10.4's Order+Stock
    asymmetry) — so cancelling it is safe as the plain single-aggregate `cancel_order`
    above, no orchestrator needed. IDs are listed in one read, then each order is
    re-fetched and cancelled in its own transaction (not one giant transaction for the
    whole batch) so one bad row can't roll back everything else in the batch."""
    with uow.transaction():
        cutoff = base_value_objects.PosixTime.now().microseconds - abandoned_after_microseconds
        stale_ids = _order_repo(uow).list_stale_pending_ids(created_before_microseconds=cutoff)

    expired = 0
    for order_id in stale_ids:
        try:
            cancel_order(uow=uow, order_id=order_id, actor=_SYSTEM_EXPIRE_ACTOR)
        except Exception:
            _LOGGER.exception("Failed to expire abandoned order [%s]", order_id)
            continue
        expired += 1
    return expired


def _order_repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultOrderRepository:
    """`uow.repo(...)` returns the generic Repository[T] port, which has no
    `list_active_for_customer` (bespoke queries stay off the generic interface,
    ARCHITECTURE.md §7). Explicit, visible cast — not a silent `# type: ignore`. Called once
    per function and reused for every `.get`/`.add`/`.update` call in it, rather than
    re-resolving `uow.repo(aggregate.Order)` (or this cast) a second time — it's the same
    cached instance either way (`UnitOfWork.repo` memoizes it), but one local variable
    reads as "this function works with one repository," not two unrelated lookups."""
    return typing.cast(repository.DefaultOrderRepository, uow.repo(aggregate.Order))
