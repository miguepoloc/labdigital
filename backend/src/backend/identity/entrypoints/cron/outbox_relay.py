"""Identity's outbox relay — ARCHITECTURE.md §11.2. Every product that emits
IntegrationEvents gets its own relay entrypoint, publishing to its own SNS topic (one topic
per product, ARCHITECTURE.md §11.2's fan-out shape)."""

from typing import Any

import boto3

from backend.commons.adapters import outbox_relay, settings, unit_of_work


class _Settings(settings.Settings):
    """This Lambda's own topic ARN, not the shared `commons.adapters.settings.Settings`
    (ARCHITECTURE.md §14.1) — commerce's own `outbox_relay.py` has an identical `_Settings`
    with its own `sns_topic_arn_commerce` field; neither Lambda needs to know the other's."""

    sns_topic_arn_identity: str = ""


_SETTINGS = _Settings()
_sns_client = boto3.client("sns")


def handler(event: dict[str, Any], context: Any) -> None:
    uow = unit_of_work.build()
    outbox_relay.publish_pending(
        uow, sns_client=_sns_client, topic_arn=_SETTINGS.sns_topic_arn_identity
    )
