"""Unit tests for `commerce.orders.services.orders` — ARCHITECTURE.md §15. Fakes only, no
Postgres: `FakeOrderRepository` (this package's own `fakes.py`) wired into `FakeUnitOfWork`,
plus `FakePricingAdapter` standing in for the external pricing port."""

import decimal
from typing import Any

import pytest

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.orders.adapters import pricing_adapter
from backend.commerce.orders.domain.model import aggregate, exceptions, value_objects
from backend.commerce.orders.services import dto, orders
from backend.commons.domain import aggregates, audit, money, value_objects as base_value_objects
from tests.unit import fakes
from tests.unit.backend.commerce.orders import fakes as order_fakes

pytestmark = pytest.mark.unit

_DEFAULT_SKU = "SKU-1"
_ACTOR = audit.Actor(id="test-actor", label="test")


def _build_uow() -> tuple[fakes.FakeUnitOfWork, order_fakes.FakeOrderRepository]:
    repos: dict[type[aggregates.AggregateRoot[Any]], Any] = {}
    uow = fakes.FakeUnitOfWork(repos=repos)
    order_repo = order_fakes.FakeOrderRepository(outbox=uow.outbox)
    repos[aggregate.Order] = order_repo
    return uow, order_repo


def _pricing_with_default_sku() -> pricing_adapter.FakePricingAdapter:
    pricing = pricing_adapter.FakePricingAdapter()
    pricing.set_price(
        commerce_value_objects.Sku(value=_DEFAULT_SKU),
        money.PositiveMoney(currency=money.Currencies.COP, value=decimal.Decimal(100)),
    )
    return pricing


def _create_order(
    uow: fakes.FakeUnitOfWork,
    pricing: pricing_adapter.FakePricingAdapter,
    *,
    customer_id: str = "cust-1",
) -> dto.OrderOutputDTO:
    return orders.create_order(
        uow=uow,
        input_dto=dto.CreateOrderInputDTO(
            customer_id=customer_id,
            lines=[dto.OrderLineInputDTO(sku=_DEFAULT_SKU, quantity=1)],
        ),
        pricing_port=pricing,
        actor=_ACTOR,
    )


def test_create_order_then_get_round_trip() -> None:
    uow, _ = _build_uow()
    created = _create_order(uow, _pricing_with_default_sku())

    fetched = orders.get_order(uow=uow, order_id=value_objects.OrderId(value=created.id))

    assert fetched.id == created.id
    assert fetched.status is value_objects.OrderStatus.PENDING
    assert uow.outbox.recorded  # OrderCreated event drained through the fake repo's add()
    assert uow.audit.entries


def test_confirm_pending_order_marks_confirmed_and_had_reserved_stock() -> None:
    uow, _ = _build_uow()
    order = _create_order(uow, _pricing_with_default_sku())

    confirmed = orders.confirm_order(
        uow=uow,
        order_id=value_objects.OrderId(value=order.id),
        shipping_name="Ada Lovelace",
        shipping_email="ada@example.com",
        actor=_ACTOR,
    )

    assert confirmed.status is value_objects.OrderStatus.CONFIRMED
    assert confirmed.had_reserved_stock is True


def test_cancel_pending_order_never_reserved_stock() -> None:
    uow, _ = _build_uow()
    order = _create_order(uow, _pricing_with_default_sku())

    cancelled = orders.cancel_order(
        uow=uow, order_id=value_objects.OrderId(value=order.id), actor=_ACTOR
    )

    assert cancelled.status is value_objects.OrderStatus.CANCELLED
    assert cancelled.had_reserved_stock is False


def test_cancel_confirmed_order_had_reserved_stock() -> None:
    uow, _ = _build_uow()
    order = _create_order(uow, _pricing_with_default_sku())
    orders.confirm_order(
        uow=uow,
        order_id=value_objects.OrderId(value=order.id),
        shipping_name="Ada Lovelace",
        shipping_email="ada@example.com",
        actor=_ACTOR,
    )

    cancelled = orders.cancel_order(
        uow=uow, order_id=value_objects.OrderId(value=order.id), actor=_ACTOR
    )

    assert cancelled.status is value_objects.OrderStatus.CANCELLED
    assert cancelled.had_reserved_stock is True


def test_cancel_already_cancelled_order_raises() -> None:
    uow, _ = _build_uow()
    order = _create_order(uow, _pricing_with_default_sku())
    orders.cancel_order(uow=uow, order_id=value_objects.OrderId(value=order.id), actor=_ACTOR)

    with pytest.raises(exceptions.OrderCannotBeCancelledError):
        orders.cancel_order(uow=uow, order_id=value_objects.OrderId(value=order.id), actor=_ACTOR)


def test_cancel_pending_orders_for_customer_only_touches_that_customers_active_orders() -> None:
    uow, order_repo = _build_uow()
    pricing = _pricing_with_default_sku()
    pending = _create_order(uow, pricing, customer_id="cust-1")
    confirmed = _create_order(uow, pricing, customer_id="cust-1")
    orders.confirm_order(
        uow=uow,
        order_id=value_objects.OrderId(value=confirmed.id),
        shipping_name="Ada Lovelace",
        shipping_email="ada@example.com",
        actor=_ACTOR,
    )
    already_cancelled = _create_order(uow, pricing, customer_id="cust-1")
    orders.cancel_order(
        uow=uow, order_id=value_objects.OrderId(value=already_cancelled.id), actor=_ACTOR
    )
    other_customer_order = _create_order(uow, pricing, customer_id="cust-2")

    cancelled_count = orders.cancel_pending_orders_for_customer(
        uow=uow, customer_id=value_objects.CustomerId(value="cust-1")
    )

    assert cancelled_count == 2
    assert (
        order_repo.get(value_objects.OrderId(value=pending.id)).status
        is value_objects.OrderStatus.CANCELLED
    )
    assert (
        order_repo.get(value_objects.OrderId(value=confirmed.id)).status
        is value_objects.OrderStatus.CANCELLED
    )
    assert (
        order_repo.get(value_objects.OrderId(value=other_customer_order.id)).status
        is value_objects.OrderStatus.PENDING
    )


def test_expire_abandoned_orders_cancels_only_stale_pending_and_survives_one_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow, order_repo = _build_uow()
    pricing = _pricing_with_default_sku()
    stale_and_broken = _create_order(uow, pricing, customer_id="cust-1")
    stale_and_fine = _create_order(uow, pricing, customer_id="cust-2")
    fresh = _create_order(uow, pricing, customer_id="cust-3")

    long_ago = base_value_objects.PosixTime(microseconds=0)
    order_repo.get(value_objects.OrderId(value=stale_and_broken.id)).created_at = long_ago
    order_repo.get(value_objects.OrderId(value=stale_and_fine.id)).created_at = long_ago
    # `fresh` keeps its real (recent) created_at, so it never appears in the stale list.

    real_get = order_repo.get

    def _poisoned_get(id: value_objects.OrderId) -> aggregate.Order:  # noqa: A002
        if id.value == stale_and_broken.id:
            raise RuntimeError("simulated failure fetching order")
        return real_get(id)

    monkeypatch.setattr(order_repo, "get", _poisoned_get)

    expired = orders.expire_abandoned_orders(uow=uow, abandoned_after_microseconds=1)

    assert expired == 1  # only the non-broken stale order actually got cancelled
    assert (
        order_repo._by_id[value_objects.OrderId(value=stale_and_fine.id)].status
        is value_objects.OrderStatus.CANCELLED
    )
    assert (
        order_repo._by_id[value_objects.OrderId(value=fresh.id)].status
        is value_objects.OrderStatus.PENDING
    )
