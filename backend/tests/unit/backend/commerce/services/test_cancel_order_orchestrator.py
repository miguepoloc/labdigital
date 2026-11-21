"""Unit tests for `commerce.services.cancel_order_orchestrator` — ARCHITECTURE.md §15. Same
fake wiring as `test_confirm_order_orchestrator.py`: `FakeOrderRepository`/
`FakeStockRepository` reused from the orders/stock unit test packages, one shared outbox."""

import decimal
from typing import Any

import pytest

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.orders.adapters import pricing_adapter, user_profile_adapter
from backend.commerce.orders.domain.model import aggregate as order_aggregate
from backend.commerce.orders.domain.model import ports
from backend.commerce.orders.domain.model import value_objects as order_value_objects
from backend.commerce.orders.services import dto as order_dto
from backend.commerce.orders.services import orders
from backend.commerce.services import cancel_order_orchestrator, confirm_order_orchestrator
from backend.commerce.stock.domain.model import aggregate as stock_aggregate
from backend.commerce.stock.services import dto as stock_dto
from backend.commerce.stock.services import stock
from backend.commons.domain import aggregates, audit, money
from tests.unit import fakes
from tests.unit.backend.commerce.orders import fakes as order_fakes
from tests.unit.backend.commerce.stock import fakes as stock_fakes

pytestmark = pytest.mark.unit

_ACTOR = audit.Actor(id="test-actor", label="test")
_CUSTOMER_ID = "cust-1"
_SKU = "SKU-1"


def _build_uow() -> tuple[
    fakes.FakeUnitOfWork, order_fakes.FakeOrderRepository, stock_fakes.FakeStockRepository
]:
    repos: dict[type[aggregates.AggregateRoot[Any]], Any] = {}
    uow = fakes.FakeUnitOfWork(repos=repos)
    order_repo = order_fakes.FakeOrderRepository(outbox=uow.outbox)
    stock_repo = stock_fakes.FakeStockRepository(outbox=uow.outbox)
    repos[order_aggregate.Order] = order_repo
    repos[stock_aggregate.Stock] = stock_repo
    return uow, order_repo, stock_repo


def _seed_stock(uow: fakes.FakeUnitOfWork, quantity: int) -> None:
    stock.create_stock(
        uow=uow,
        input_dto=stock_dto.CreateStockInputDTO(sku=_SKU, initial_quantity=quantity),
        actor=_ACTOR,
    )


def _create_order(uow: fakes.FakeUnitOfWork, quantity: int) -> order_dto.OrderOutputDTO:
    pricing = pricing_adapter.FakePricingAdapter()
    pricing.set_price(
        commerce_value_objects.Sku(value=_SKU),
        money.PositiveMoney(currency=money.Currencies.COP, value=decimal.Decimal(100)),
    )
    return orders.create_order(
        uow=uow,
        input_dto=order_dto.CreateOrderInputDTO(
            customer_id=_CUSTOMER_ID,
            lines=[order_dto.OrderLineInputDTO(sku=_SKU, quantity=quantity)],
        ),
        pricing_port=pricing,
        actor=_ACTOR,
    )


def _profile_port() -> user_profile_adapter.FakeUserProfileAdapter:
    profile_port = user_profile_adapter.FakeUserProfileAdapter()
    profile_port.set_profile(
        order_value_objects.CustomerId(value=_CUSTOMER_ID),
        ports.UserProfile(full_name="Ada Lovelace", email="ada@example.com"),
    )
    return profile_port


def test_cancel_confirmed_order_releases_stock() -> None:
    uow, _, stock_repo = _build_uow()
    _seed_stock(uow, 10)
    order = _create_order(uow, quantity=4)
    confirm_order_orchestrator.confirm_order(
        uow=uow,
        order_id=order_value_objects.OrderId(value=order.id),
        user_profile_port=_profile_port(),
        actor=_ACTOR,
    )
    assert stock_repo.get_by_sku(commerce_value_objects.Sku(value=_SKU)).available_quantity == 6

    cancelled = cancel_order_orchestrator.cancel_order(
        uow=uow, order_id=order_value_objects.OrderId(value=order.id), actor=_ACTOR
    )

    assert cancelled.status is order_value_objects.OrderStatus.CANCELLED
    assert stock_repo.get_by_sku(commerce_value_objects.Sku(value=_SKU)).available_quantity == 10


def test_cancel_pending_order_never_reserved_does_not_touch_stock() -> None:
    uow, _, stock_repo = _build_uow()
    _seed_stock(uow, 10)
    order = _create_order(uow, quantity=4)  # never confirmed — stays PENDING

    cancelled = cancel_order_orchestrator.cancel_order(
        uow=uow, order_id=order_value_objects.OrderId(value=order.id), actor=_ACTOR
    )

    assert cancelled.status is order_value_objects.OrderStatus.CANCELLED
    assert cancelled.had_reserved_stock is False
    assert stock_repo.get_by_sku(commerce_value_objects.Sku(value=_SKU)).available_quantity == 10
