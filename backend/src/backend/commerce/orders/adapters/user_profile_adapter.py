"""Internal synchronous port implementation — ARCHITECTURE.md §9.2/§10.2b. Calls another
product's entrypoints/web/internal.py over HTTP, with service-to-service auth (an API key
header, never the customer's own JWT)."""

import backoff
import httpx
import pydantic

from backend.commerce.orders.domain.model import ports, value_objects
from backend.commons.adapters import settings
from backend.commons.domain import exceptions

_RETRYABLE_ERRORS = (httpx.ConnectTimeout, httpx.ReadTimeout)


class _Settings(settings.Settings):
    """This module's own local settings — ARCHITECTURE.md §14.1, same reasoning as
    `pricing_adapter._Settings`. `identity_internal_api_base_url` has exactly one consumer
    (`HttpUserProfileAdapter`, right below); `internal_api_key` is inherited from the shared
    `Settings` unchanged (it has a second consumer, `identity/entrypoints/web
    /_dependencies.py::require_service_auth` — a real cross-product concern, so it stays on
    the shared class) — one `_SETTINGS` instance here covers both without a second
    `settings.get_settings()` call."""

    identity_internal_api_base_url: str


_SETTINGS = _Settings()


class _ProfileResponseDTO(pydantic.BaseModel):
    """Validates identity's JSON shape before it touches domain code — same split as
    `pricing_adapter._PriceResponseDTO`, verified against bold's mapper convention
    (ARCHITECTURE.md §10.2a/§10.2b)."""

    full_name: str
    email: str


class ProfileNotConfiguredError(exceptions.NotFoundError):
    """Raised by `FakeUserProfileAdapter` for a customer id it wasn't told about — same
    fail-loud reasoning, and same `NotFoundError` base, as
    `pricing_adapter.PriceNotConfiguredError` (ARCHITECTURE.md §13)."""

    def __init__(self, customer_id: str) -> None:
        super().__init__(
            f"No fake profile configured for customer [{customer_id}].",
            code="PROFILE_NOT_CONFIGURED",
        )


class FakeUserProfileAdapter(ports.UserProfilePort):
    """Returned by `_get_user_profile_port()` (`entrypoints/web/orders.py`) instead of
    `HttpUserProfileAdapter` whenever `Settings.use_fake_external_adapters` is true
    (`adapters/adapter_factory.py`) — so DEV/STAGING Lambdas, and unit tests that construct
    this directly, never depend on identity's internal API being reachable. Same shape as
    `pricing_adapter.FakePricingAdapter`."""

    def __init__(self, profiles: dict[str, ports.UserProfile] | None = None) -> None:
        self._profiles = dict(profiles or {})

    def set_profile(
        self, customer_id: value_objects.CustomerId, profile: ports.UserProfile
    ) -> None:
        self._profiles[customer_id.value] = profile

    def get_profile(self, customer_id: value_objects.CustomerId) -> ports.UserProfile:
        try:
            return self._profiles[customer_id.value]
        except KeyError:
            raise ProfileNotConfiguredError(customer_id.value) from None


class HttpUserProfileAdapter(ports.UserProfilePort):
    def __init__(self, *, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self._base_url = base_url or _SETTINGS.identity_internal_api_base_url
        self._client = client or httpx.Client(timeout=5.0)

    @backoff.on_exception(backoff.expo, _RETRYABLE_ERRORS, jitter=backoff.full_jitter, max_tries=3)
    def get_profile(self, customer_id: value_objects.CustomerId) -> ports.UserProfile:
        response = self._client.get(
            f"{self._base_url}/internal/users/{customer_id.value}/profile",
            headers={"X-Internal-Api-Key": _SETTINGS.internal_api_key},
        )
        response.raise_for_status()
        payload = _ProfileResponseDTO.model_validate(response.json())
        return ports.UserProfile(full_name=payload.full_name, email=payload.email)
