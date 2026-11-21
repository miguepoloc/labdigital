"""External synchronous port implementation — ARCHITECTURE.md §10.2a. Modeled on bold's
BreBCashinPricingAdapter: an external price lookup, called from application code, with the
result handed to the aggregate as a plain parameter."""

import decimal

import backoff
import httpx
import pydantic

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.orders.domain.model import ports
from backend.commons.adapters import settings
from backend.commons.domain import exceptions, money

_RETRYABLE_ERRORS = (httpx.ConnectTimeout, httpx.ReadTimeout)


class _Settings(settings.Settings):
    """This module's own local settings — ARCHITECTURE.md §14.1. `pricing_service_base_url`
    has exactly one consumer (`HttpPricingAdapter`, right below), so it lives here, not on
    the shared `commons.adapters.settings.Settings`: bold's own convention for single-consumer
    config (`class _Settings(commons_settings.Settings)`, one per file that needs it, e.g.
    `accounting/loans/revolving/adapters/biometric_identity_provider.py`), not this
    template's own invention."""

    pricing_service_base_url: str


_SETTINGS = _Settings()


class _PriceResponseDTO(pydantic.BaseModel):
    """Validates the pricing service's JSON shape before it touches domain code — verified
    against bold's `mappers.map_response_to_...` split: parse into a typed response DTO
    first, only then convert into the domain value object (ARCHITECTURE.md §10.2a)."""

    currency: str
    unit_price: decimal.Decimal


class PriceNotConfiguredError(exceptions.NotFoundError):
    """Raised by `FakePricingAdapter` for a sku it wasn't told about — a loud failure, not a
    silently-invented price, so a DEV/STAGING request against an unseeded sku fails the same
    way a real pricing-service 404 would, instead of returning a number nobody chose.
    Subclasses `commons.domain.exceptions.NotFoundError`, not bare `Exception` — every domain
    exception in this codebase goes through that one vocabulary (ARCHITECTURE.md §13), the
    same rule `commerce/stock/domain/model/exceptions.py::StockNotFoundError` follows for the
    real "not found" case this fake stands in for."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"No fake price configured for sku [{sku}].", code="PRICE_NOT_CONFIGURED")


class FakePricingAdapter(ports.PricingPort):
    """Returned by `_get_pricing_port()` (`entrypoints/web/orders.py`) instead of
    `HttpPricingAdapter` whenever `Settings.use_fake_external_adapters` is true
    (`adapters/adapter_factory.py`) — so DEV/STAGING Lambdas, and unit tests that construct
    this directly, never depend on a real pricing service being reachable. Modeled on bold's
    `deposit/breb/adapters/fake.py::FakeBreBAdapter`: an in-memory, explicitly-seeded stand-in
    implementing the exact same port, not a `unittest.mock.Mock` — a caller gets a real
    `PositiveMoney` back, not an assertion helper. `prices` defaults to `{}`, not some made-up
    non-zero price: a test/DEV run either seeds the skus it needs or gets
    `PriceNotConfiguredError`, on the same theory as bold's `FakeBreBAdapter` sentinel values
    — a fake that improvises an answer for unrecognized input hides bugs instead of catching
    them."""

    def __init__(self, prices: dict[str, money.PositiveMoney] | None = None) -> None:
        self._prices = dict(prices or {})

    def set_price(self, sku: commerce_value_objects.Sku, price: money.PositiveMoney) -> None:
        self._prices[sku.value] = price

    def get_unit_price(self, sku: commerce_value_objects.Sku) -> money.PositiveMoney:
        try:
            return self._prices[sku.value]
        except KeyError:
            raise PriceNotConfiguredError(sku.value) from None


class HttpPricingAdapter(ports.PricingPort):
    def __init__(self, *, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self._base_url = base_url or _SETTINGS.pricing_service_base_url
        self._client = client or httpx.Client(timeout=5.0)

    @backoff.on_exception(backoff.expo, _RETRYABLE_ERRORS, jitter=backoff.full_jitter, max_tries=3)
    def get_unit_price(self, sku: commerce_value_objects.Sku) -> money.PositiveMoney:
        response = self._client.get(f"{self._base_url}/prices/{sku.value}")
        response.raise_for_status()
        payload = _PriceResponseDTO.model_validate(response.json())
        return money.PositiveMoney(
            currency=money.Currencies(payload.currency), value=payload.unit_price
        )
