"""Audit log — ARCHITECTURE.md §14.2. Append-only record of who did what, shared by every
product via `commons/` (verified against bold's `commons/base_types.py::AuditLog`, embedded
in every `AuditableEvent`, and `sona-sso-backend`'s dedicated `audit` bounded context — both
put the shared vocabulary in the layer every product can already reach, never duplicated
per product).

`aggregate_type`/`aggregate_id` are plain `str`, not a typed value object: `commons/` cannot
import any product's domain (import-linter contract 4), and one column can't hold a real
Postgres FK to `orders`, `stock`, and `users` simultaneously anyway — nor would you want
one, since deleting the referenced aggregate must never delete or orphan its own audit
trail. Each product declares its own local `AuditAggregateType` enum and passes `.value` in,
mirroring how each product already owns its own `AuditAction`-shaped constants — growth of
"what can be audited" happens in the product that grew, never in this file. Named
`aggregate_type`/`aggregate_id`, not `entity_type`/`entity_id`: this codebase already
distinguishes `Entity[IdT]` from `AggregateRoot[IdT]` (`commons/domain/entities.py` vs
`aggregates.py`), and every audit-writing call site sits right where `uow.repo(...).add`/
`.update` does — always the aggregate root being persisted, never a child entity inside it.

`Actor.id` is a plain `str`, not a typed value object — `HumanFriendlyId` doesn't validate
format (no `field_validator`), so wrapping it bought no real guarantee over `str`, and the
actor isn't always a `User` anyway: a call authenticated by `INTERNAL_API_KEY`
(service-to-service, §9.2) has no `UserId` to wrap at all.

`Actor` is its own value object, not two loose `actor_id`/`actor_label` parameters
threaded through every service function: it comes from exactly one place — the verified
JWT (or `INTERNAL_API_KEY`) at the entrypoint's composition root — never from a request-body
DTO (`CreateOrderInputDTO` and friends carry only what the *client* sent; trusting a
client-supplied actor id would let any caller claim to be anyone). An entrypoint builds one
`Actor` and threads it down through the orchestrator/service call, the same way it already
threads a `PricingPort`/`UserProfilePort` instance rather than passing its constructor
arguments separately.
"""

from typing import Any

import pydantic

from backend.commons.domain import value_objects


class Actor(value_objects.ValueObject):
    """`id` is `None` for system-initiated entries (a cron job, not a human request);
    `label` is always set — a human-readable snapshot (e.g. an email) taken at write time,
    so the entry stays legible even after the referenced user is later deleted or renamed."""

    id: str | None
    label: str


class AuditEntry(value_objects.ValueObject):
    """One append-only record. `id` is assigned by Postgres (`BigInteger Identity`), not a
    `HumanFriendlyId` like every other aggregate's id: an unbounded, ever-growing log is
    exactly the case a random-10-character scheme isn't sized for — verified against
    `sona-sso-backend`'s own `audit/adapters/orm.py` docstring, same reasoning.

    No FK from either `actor.id` or `aggregate_id` to the row it names, on purpose: this log
    must survive the referenced row's own lifecycle."""

    id: int | None = None
    actor: Actor
    action: str
    aggregate_type: str
    aggregate_id: str
    changes: dict[str, Any] = pydantic.Field(default_factory=dict)
    created_at: value_objects.PosixTime = pydantic.Field(
        default_factory=value_objects.PosixTime.now
    )
