"""The Outbox relay — ARCHITECTURE.md §11.2. A separate module from outbox.py (not a
circular-import workaround so much as a real layering point: OutboxRepository is a plain
persistence adapter used from inside a transaction; the relay is the cron-triggered process
that reads it and calls out to SNS, a distinct responsibility with its own dependency
(boto3, a UnitOfWork) neither outbox.py nor unit_of_work.py needs to know about).

Deliberately three steps, not one transaction: `sns_client.publish` is external I/O, and
`persistence-and-concurrency.md` §8's "no I/O inside an open transaction" rule (the same rule
`services/orders.py::confirm_order` was fixed for once already, `anti-patterns-and-design-
principles.md` §20) applies here too — a row's `with_for_update(skip_locked=True)` lock has
no business being held open for the duration of N network calls to SNS. Reading the batch and
publishing it can race across two concurrent relay invocations (the read-lock is released at
step 1's commit, before step 3 marks rows published) — accepted deliberately: every
IntegrationEvent consumer is required to be idempotent already (CLAUDE.md, §12), so an
occasional duplicate publish is a non-event downstream, not a correctness bug."""

import json
import uuid

from mypy_boto3_sns.client import SNSClient

from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import events

_LOGGER = logs.get_logger()
_INTEGRATION_EVENT_TYPES = {cls.__name__ for cls in events.IntegrationEvent.__subclasses__()}


def publish_pending(uow: unit_of_work.UnitOfWork, *, sns_client: SNSClient, topic_arn: str) -> int:
    """Cron-triggered (identity/entrypoints/cron, commerce/entrypoints/cron — see each
    product's own relay entrypoint), one call per invocation, polling every 10-30s (bold's
    EventsClient interval). Only IntegrationEvent rows leave the process; purely-internal
    DomainEvent rows are marked published without ever reaching SNS (§11.1)."""
    to_publish: list[tuple[uuid.UUID, str, dict]] = []
    with uow.transaction():
        for row in uow.outbox.unpublished():
            if row.event_type not in _INTEGRATION_EVENT_TYPES:
                uow.outbox.mark_published(row)  # not relayed, but not retried forever either
                continue
            to_publish.append((row.id, row.event_type, row.payload))

    # SNS calls happen with no transaction open — see the module docstring.
    published_ids: list[uuid.UUID] = []
    for row_id, event_type, payload in to_publish:
        sns_client.publish(
            TopicArn=topic_arn,
            Message=json.dumps(payload, default=str),
            MessageAttributes={"event_type": {"DataType": "String", "StringValue": event_type}},
        )
        published_ids.append(row_id)

    if published_ids:
        with uow.transaction():
            uow.outbox.mark_many_published(published_ids)

    published_count = len(published_ids)
    if published_count:
        _LOGGER.info("Outbox relay published %s event(s)", published_count)
    return published_count
