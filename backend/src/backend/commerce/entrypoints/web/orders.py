"""OrdersLambda — ARCHITECTURE.md §9.1. Customer-facing; JWT required.

One file per subcontext, one subcontext per Lambda — orders and stock are independent
bounded contexts (ARCHITECTURE.md §10.4) with independent deploy/scale lifecycles, so they
never share a router the way this file and `stock.py` used to before being split (verified
against sona-sso-backend's `entrypoints/web/organizations.py` vs `sso_connections.py`: two
subcontexts sharing one product never share one router file either, even when a third
Lambda later composes both, ARCHITECTURE.md §16.1)."""

from typing import Annotated

import fastapi
from fastapi import status
import mangum

from backend.commerce.entrypoints.web import _dependencies
from backend.commerce.orders.adapters import pricing_adapter, user_profile_adapter
from backend.commerce.orders.domain.model import ports
from backend.commerce.orders.domain.model import value_objects as order_value_objects
from backend.commerce.orders.services import dto as orders_dto
from backend.commerce.orders.services import orders
from backend.commerce.services import cancel_order_orchestrator, confirm_order_orchestrator
from backend.commons.adapters import adapter_factory, authentication, unit_of_work
from backend.commons.adapters.api import exception_handler, middleware
from backend.commons.domain import audit

app = fastapi.FastAPI(title="Commerce — Orders API")
app.add_middleware(middleware.RequestLoggingMiddleware)
exception_handler.install(app)

UowDep = Annotated[unit_of_work.UnitOfWork, fastapi.Depends(_dependencies.get_uow)]
UserDep = Annotated[authentication.AuthenticatedUser, fastapi.Depends(_dependencies.require_jwt)]


def _get_pricing_port() -> ports.PricingPort:
    """Composition root for `PricingPort` — ARCHITECTURE.md §10.2a, matching bold's
    `_get_breb_cashin_pricing_adapter()`: the concrete adapter is built here, once, at the
    entrypoint, and threaded into the service call explicitly. `services/orders.py` never
    constructs its own adapter or falls back to a default — that would hide the dependency
    instead of wiring it. `get_adapter()` picks `FakePricingAdapter` over
    `HttpPricingAdapter` outside PROD (`adapter_factory.py`, verified against bold's real
    `deposit/breb` fake/real adapter split) — this Lambda never depends on a real pricing
    service being reachable in DEV/STAGING."""
    return adapter_factory.get_adapter(
        default_factory=pricing_adapter.HttpPricingAdapter,
        fake_factory=pricing_adapter.FakePricingAdapter,
    )


def _get_user_profile_port() -> ports.UserProfilePort:
    """Composition root for `UserProfilePort` — same reasoning as `_get_pricing_port` above,
    ARCHITECTURE.md §10.2b."""
    return adapter_factory.get_adapter(
        default_factory=user_profile_adapter.HttpUserProfileAdapter,
        fake_factory=user_profile_adapter.FakeUserProfileAdapter,
    )


@app.post("/orders", response_model=orders_dto.OrderOutputDTO, status_code=status.HTTP_201_CREATED)
def create_order(
    body: orders_dto.CreateOrderInputDTO, uow: UowDep, user: UserDep
) -> orders_dto.OrderOutputDTO:
    return orders.create_order(
        uow=uow,
        input_dto=body,
        pricing_port=_get_pricing_port(),
        actor=audit.Actor(id=user.user_id, label=user.user_id),
    )


@app.get("/orders/{order_id}", response_model=orders_dto.OrderOutputDTO)
def get_order(order_id: str, uow: UowDep, _user: UserDep) -> orders_dto.OrderOutputDTO:
    return orders.get_order(uow=uow, order_id=order_value_objects.OrderId(value=order_id))


@app.post("/orders/{order_id}/confirm", response_model=orders_dto.OrderOutputDTO)
def confirm_order(order_id: str, uow: UowDep, user: UserDep) -> orders_dto.OrderOutputDTO:
    return confirm_order_orchestrator.confirm_order(
        uow=uow,
        order_id=order_value_objects.OrderId(value=order_id),
        user_profile_port=_get_user_profile_port(),
        actor=audit.Actor(id=user.user_id, label=user.user_id),
    )


@app.post("/orders/{order_id}/cancel", response_model=orders_dto.OrderOutputDTO)
def cancel_order(order_id: str, uow: UowDep, user: UserDep) -> orders_dto.OrderOutputDTO:
    return cancel_order_orchestrator.cancel_order(
        uow=uow,
        order_id=order_value_objects.OrderId(value=order_id),
        actor=audit.Actor(id=user.user_id, label=user.user_id),
    )


handler = mangum.Mangum(app)
