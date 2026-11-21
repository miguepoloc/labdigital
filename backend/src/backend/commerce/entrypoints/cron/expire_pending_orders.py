"""EventBridge-scheduled — ARCHITECTURE.md §9.5/§18. Housekeeping: cancels orders left in
PENDING for too long (abandoned checkouts), so they don't linger forever."""

import datetime
from typing import Any

from backend.commerce.orders.services import orders
from backend.commons.adapters import logs, unit_of_work

_LOGGER = logs.get_logger()
_ABANDONED_AFTER = datetime.timedelta(hours=24)


def handler(event: dict[str, Any], context: Any) -> None:
    expired = orders.expire_abandoned_orders(
        uow=unit_of_work.build(),
        abandoned_after_microseconds=int(_ABANDONED_AFTER.total_seconds() * 1_000_000),
    )
    _LOGGER.info("Expired %s abandoned pending order(s)", expired)
