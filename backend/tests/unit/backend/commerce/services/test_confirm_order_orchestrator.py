"""Unit tests for `commerce.services.confirm_order_orchestrator` — ARCHITECTURE.md §15.
Reuses `FakeOrderRepository`/`FakeStockRepository` from the orders/stock unit test packages
(never duplicated here) plus `FakeUserProfileAdapter`, all wired into one `FakeUnitOfWork`
sharing a single outbox — the same shape the real orchestrator relies on when it threads one
`uow` across two subcontexts' `services/` calls (§10.2)."""

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
from backend.commerce.services import confirm_order_orchestrator
from backend.commerce.stock.domain.model import aggregate as stock_aggregate
from backend.commerce.stock.domain.model import exceptions as stock_exceptions
from backend.commerce.stock.services import dto as stock_dto
from backend.commerce.stock.services import stock
from backend.commons.domain import aggregates, audit, money
from tests.unit import fakes
from tests.unit.backend.commerce.orders import fakes as order_fakes
from tests.unit.backend.commerce.stock import fakes as stock_fakes

pytestmark = pytest.mark.unit

_ACTOR = audit.Actor(id="test-actor", label="test")
_CUSTOMER_ID = "cust-1"


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


def _seed_stock(uow: fakes.FakeUnitOfWork, sku: str, quantity: int) -> None:
    stock.create_stock(
        uow=uow,
        input_dto=stock_dto.CreateStockInputDTO(sku=sku, initial_quantity=quantity),
        actor=_ACTOR,
    )


def _pricing_for(*skus: str) -> pricing_adapter.FakePricingAdapter:
    pricing = pricing_adapter.FakePricingAdapter()
    for sku in skus:
        pricing.set_price(
            commerce_value_objects.Sku(value=sku),
            money.PositiveMoney(currency=money.Currencies.COP, value=decimal.Decimal(100)),
        )
    return pricing


def _create_order(
    uow: fakes.FakeUnitOfWork,
    pricing: pricing_adapter.FakePricingAdapter,
    lines: list[tuple[str, int]],
) -> order_dto.OrderOutputDTO:
    return orders.create_order(
        uow=uow,
        input_dto=order_dto.CreateOrderInputDTO(
            customer_id=_CUSTOMER_ID,
            lines=[order_dto.OrderLineInputDTO(sku=sku, quantity=qty) for sku, qty in lines],
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


def test_confirm_order_reserves_stock_for_every_line() -> None:
    uow, _, stock_repo = _build_uow()
    _seed_stock(uow, "SKU-1", 10)
    _seed_stock(uow, "SKU-2", 5)
    order = _create_order(uow, _pricing_for("SKU-1", "SKU-2"), [("SKU-1", 2), ("SKU-2", 3)])

    confirmed = confirm_order_orchestrator.confirm_order(
        uow=uow,
        order_id=order_value_objects.OrderId(value=order.id),
        user_profile_port=_profile_port(),
        actor=_ACTOR,
    )

    assert confirmed.status is order_value_objects.OrderStatus.CONFIRMED
    assert stock_repo.get_by_sku(commerce_value_objects.Sku(value="SKU-1")).available_quantity == 8
    assert stock_repo.get_by_sku(commerce_value_objects.Sku(value="SKU-2")).available_quantity == 2


def test_confirm_order_with_insufficient_stock_raises_and_does_not_confirm() -> None:
    uow, order_repo, _ = _build_uow()
    _seed_stock(uow, "SKU-1", 10)
    _seed_stock(uow, "SKU-2", 1)  # not enough for the order's line quantity of 3
    order = _create_order(uow, _pricing_for("SKU-1", "SKU-2"), [("SKU-1", 2), ("SKU-2", 3)])

    with pytest.raises(stock_exceptions.InsufficientStockError):
        confirm_order_orchestrator.confirm_order(
            uow=uow,
            order_id=order_value_objects.OrderId(value=order.id),
            user_profile_port=_profile_port(),
            actor=_ACTOR,
        )

    # The exception propagates out of the orchestrator (not swallowed by the try/except
    # around the per-line stock.reserve_stock call), and the order was never confirmed.
    assert (
        order_repo.get(order_value_objects.OrderId(value=order.id)).status
        is order_value_objects.OrderStatus.PENDING
    )
