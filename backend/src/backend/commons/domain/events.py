"""Domain/integration event hierarchy — ARCHITECTURE.md §11.1."""

import json
from typing import Any
import uuid

import pydantic

from backend.commons.domain import value_objects


class DomainEvent(value_objects.ValueObject):
    event_id: uuid.UUID = pydantic.Field(default_factory=uuid.uuid4)
    occurred_at: value_objects.PosixTime = pydantic.Field(
        default_factory=value_objects.PosixTime.now
    )

    @pydantic.computed_field  # type: ignore[prop-decorator]
    @property
    def event_type(self) -> str:
        """The ONE source of truth for this event's wire name — never hand-maintain a
        parallel string constant for this (see ARCHITECTURE.md §9.4/§11.1 for why)."""
        return type(self).__name__

    def idempotence_key(self) -> str:
        """Override when a business key is more meaningful than event_id."""
        return f"{type(self).__name__}-{self.event_id}"


class IntegrationEvent(DomainEvent):
    """A DomainEvent promoted to cross a bounded-context boundary — its own class, a public
    contract. Only IntegrationEvent subclasses are ever relayed out of the outbox (§11.2)."""


def parse_envelope(body: str) -> dict[str, Any]:
    """json.loads + a minimal shape check — no event class resolved yet (ARCHITECTURE.md
    §9.4). The caller looks up `envelope["event_type"]` against its own `EventConsumer`
    registry before calling `event_class.model_validate(envelope)`."""
    envelope = json.loads(body)
    if not isinstance(envelope, dict) or "event_type" not in envelope:
        raise ValueError("SQS message body is not a valid event envelope (missing event_type).")
    return envelope
