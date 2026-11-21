"""Outbound synchronous ports — ARCHITECTURE.md §5.6/§10.2. The domain declares what it
needs; adapters/ provides it. Never called from the aggregate itself (§5.3). `PricingPort`
is called from services/orders.py (single-aggregate use case, §10.1); `UserProfilePort` is
called from services/confirm_order_orchestrator.py, BEFORE it opens its transaction — never
from inside services/orders.py itself (ARCHITECTURE.md §8's "no I/O inside an open
transaction" rule, §10.2b)."""

import abc

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.orders.domain.model import value_objects
from backend.commons.domain import money
from backend.commons.domain import value_objects as base_value_objects


class UserProfile(base_value_objects.ValueObject):
    """The shape `UserProfilePort.get_profile` returns — a `ValueObject` (Pydantic, frozen),
    not a plain `dataclass`: this data crosses a real boundary (the adapter parses it out of
    an HTTP response, §10.2b) before `orders.confirm_order` freezes it onto the aggregate, so
    it needs the same validation `ValueObject` gives every other domain type — verified
    against bold's real analog, `AuthResponseBody`, which is `base_types.ValueObject`
    (Pydantic) for exactly this reason: adapter-output data handed to application code, not
    an in-process-only structure like `EventConsumer` (§17.3's actual dataclass case — a
    `type`+`Callable` pairing built directly in Python code, never assembled from parsed
    external input)."""

    full_name: str
    email: str


class PricingPort(abc.ABC):
    """§10.2a — external synchronous port. Fetches the current unit price for a SKU, so
    services/orders.py can snapshot it onto each OrderLine at order-creation time (a later
    price change must not rewrite historical orders — the same reasoning as §9.2)."""

    @abc.abstractmethod
    def get_unit_price(self, sku: commerce_value_objects.Sku) -> money.PositiveMoney: ...


class UserProfilePort(abc.ABC):
    """§10.2b — internal synchronous port. Fetches a point-in-time snapshot of the
    customer's profile from identity's internal.py, used ONLY to freeze shipping details
    onto the order at confirmation time — never to check whether the customer exists or is
    active (the JWT already proves that, §9.2/§9.3)."""

    @abc.abstractmethod
    def get_profile(self, customer_id: value_objects.CustomerId) -> UserProfile: ...
