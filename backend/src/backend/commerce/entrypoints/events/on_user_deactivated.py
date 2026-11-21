"""ARCHITECTURE.md §9.4/§10.3 — commerce reacts asynchronously to identity's
UserDeactivated IntegrationEvent, idempotently (§12.2). No business logic here — one
deserialize, one idempotency-guarded call into orders' own services/ module."""

from typing import Any

from backend.commerce.orders.domain.model import value_objects as order_value_objects
from backend.commerce.orders.services import orders
from backend.commons.adapters import logs, sqs, unit_of_work
from backend.identity.users.domain.model import events as user_events

_LOGGER = logs.get_logger()


def _handle_user_deactivated(
    uow: unit_of_work.UnitOfWork, deactivated: user_events.UserDeactivated
) -> None:
    # Both UserId and CustomerId are HumanFriendlyId (str) — CustomerId mirrors UserId's own
    # value shape (ARCHITECTURE.md §5.2), so no conversion is needed, just a straight copy.
    customer_id = order_value_objects.CustomerId(value=deactivated.user_id.value)
    cancelled = orders.cancel_pending_orders_for_customer(uow=uow, customer_id=customer_id)
    _LOGGER.info("Cancelled %s pending order(s) for deactivated user [%s]", cancelled, customer_id)


_CONSUMERS = [
    sqs.EventConsumer(event_class=user_events.UserDeactivated, handle=_handle_user_deactivated),
]


def handler(event: dict[str, Any], context: Any) -> None:
    sqs.process_sqs_event(
        event=event, consumers=_CONSUMERS, consumer_name="commerce-on-user-deactivated"
    )
