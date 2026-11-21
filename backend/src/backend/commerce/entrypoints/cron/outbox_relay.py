"""Commerce's outbox relay — ARCHITECTURE.md §11.2. Mirrors
identity/entrypoints/cron/outbox_relay.py — one relay entrypoint per product, publishing to
that product's own SNS topic."""

from typing import Any

import boto3

from backend.commons.adapters import outbox_relay, settings, unit_of_work


class _Settings(settings.Settings):
    """This Lambda's own topic ARN, not the shared `commons.adapters.settings.Settings`
    (ARCHITECTURE.md §14.1) — identity's own `outbox_relay.py` has an identical `_Settings`
    with its own `sns_topic_arn_identity` field; neither Lambda needs to know the other's."""

    sns_topic_arn_commerce: str = ""


_SETTINGS = _Settings()
_sns_client = boto3.client("sns")


def handler(event: dict[str, Any], context: Any) -> None:
    uow = unit_of_work.build()
    outbox_relay.publish_pending(
        uow, sns_client=_sns_client, topic_arn=_SETTINGS.sns_topic_arn_commerce
    )
