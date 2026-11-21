"""EventBridge-scheduled — ARCHITECTURE.md §9.5/§18. One of the few cron jobs that's
load-bearing rather than pure housekeeping: §9.3's 'no synchronous existence check' design
relies on refresh tokens actually expiring/getting swept."""

from typing import Any

from backend.commons.adapters import logs, unit_of_work
from backend.identity.users.services import auth

_LOGGER = logs.get_logger()


def handler(event: dict[str, Any], context: Any) -> None:
    deleted = auth.expire_refresh_tokens(uow=unit_of_work.build())
    _LOGGER.info("Expired %s stale refresh token row(s)", deleted)
