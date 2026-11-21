import enum

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commons.domain import money, value_objects


class OrderId(value_objects.HumanFriendlyId):
    """Deliberately `HumanFriendlyId`, not the `UuidV7Id` default (ARCHITECTURE.md §5.2's
    "use `HumanFriendlyId` only when the ID is genuinely user-facing") — an `Order` is
    exactly that: a customer reads this ID off a receipt, quotes it in a support call, or
    it's printed on a packing slip. Verified against bold's real selection: `LoanId` and
    `BancolombiaCardlessCashout`'s `CashoutId` — both "a specific transaction a customer
    would reference by ID" — are `base_types.HumanFriendlyId`; `Stock.id` (never shown to a
    customer — `Sku` is the human-facing identifier there) stays `UuidV7Id`."""


class CustomerId(value_objects.HumanFriendlyId):
    """Deliberately NOT identity.users.domain.model.value_objects.UserId — orders owns its
    own local representation of 'whoever placed this order' rather than importing another
    product's domain type. Cross-product typed-ID sharing would couple two independently
    deployable systems at the type level, which is exactly what ARCHITECTURE.md §10.3
    argues against for cross-product transactions; the same reasoning applies to types.

    `HumanFriendlyId`, matching `identity.users.UserId`'s real underlying representation —
    not independently chosen. This is a different TYPE (per the decoupling reasoning above)
    holding the same VALUE as the real user's id (`on_user_deactivated.py` reconstructs a
    `CustomerId` directly from `UserDeactivated.user_id.value` to find that customer's
    orders, ARCHITECTURE.md §10.3) — so it must match `UserId`'s value *shape*, whatever that
    happens to be, even while staying a distinct type. `UserId` moved to `HumanFriendlyId`
    (§5.2) specifically because it's user-facing; this had to follow, or
    `uuid.UUID(a_human_friendly_id_string)` would raise `ValueError` at runtime the first
    time a real (non-UUID-shaped) id reached it — found by tracing the change through, not
    by mypy, which has no way to catch "these two independently-declared types must share a
    value format" — that constraint lives only in the domain, not the type system."""


class OrderStatus(enum.StrEnum):
    """`enum.auto()`, not a repeated lowercase string per member — `StrEnum` overrides
    `_generate_next_value_` to produce the lowercased member name, so `PENDING = enum.auto()`
    already gives `.value == "pending"`, no `"pending"` typed twice. Only safe when the
    member name IS the desired value lowercased — `money.Currencies` below deliberately does
    NOT use this (ISO-4217 codes are uppercase; `auto()` would silently produce `"cop"`
    instead of `"COP"`)."""

    PENDING = enum.auto()
    CONFIRMED = enum.auto()
    CANCELLED = enum.auto()


class OrderLine(value_objects.ValueObject):
    sku: commerce_value_objects.Sku
    quantity: int
    unit_price: money.PositiveMoney


class AuditAggregateType(enum.StrEnum):
    """Local to `commerce.orders` — `commons.domain.audit.AuditEntry.aggregate_type` stores
    whatever `.value` this produces, but `commons/` never imports this enum (contract 4)."""

    ORDER = enum.auto()


class AuditAction(enum.StrEnum):
    """Same rule as `AuditAggregateType` — grows here, not in `commons/`."""

    CREATED = enum.auto()
    CONFIRMED = enum.auto()
    CANCELLED = enum.auto()
