import enum

from backend.commons.domain import value_objects


class StockId(value_objects.UuidV7Id):
    pass


class AuditAggregateType(enum.StrEnum):
    """Local to `commerce.stock` — `commons.domain.audit.AuditEntry.aggregate_type` stores
    whatever `.value` this produces, but `commons/` never imports this enum (contract 4)."""

    STOCK = enum.auto()


class AuditAction(enum.StrEnum):
    """Same rule as `AuditAggregateType` — grows here, not in `commons/`."""

    CREATED = enum.auto()
    RESERVED = enum.auto()
    RELEASED = enum.auto()
