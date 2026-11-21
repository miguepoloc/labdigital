"""Product-local shared kernel — ARCHITECTURE.md §3.2. `Sku` is used by both
commerce/orders and commerce/stock; it lives here, not duplicated in each subcontext, and
not promoted to the global commons/ since no other product needs it (yet)."""

from backend.commons.domain import value_objects


class Sku(value_objects.ValueObject):
    value: str

    def __str__(self) -> str:
        return self.value
