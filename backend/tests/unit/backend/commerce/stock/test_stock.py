"""Unit tests for `commerce.stock.services.stock` — ARCHITECTURE.md §15. Fakes only, no
Postgres. Also verifies the try/except added around `Stock.reserve`/`.release` in
`services/stock.py` (log + re-raise) doesn't change the exception type or shape that
propagates to the caller."""

from typing import Any

import pytest

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.stock.domain.model import aggregate, exceptions
from backend.commerce.stock.services import dto, stock
from backend.commons.domain import aggregates, audit
from tests.unit import fakes
from tests.unit.backend.commerce.stock import fakes as stock_fakes

pytestmark = pytest.mark.unit

_SKU = commerce_value_objects.Sku(value="SKU-1")
_ACTOR = audit.Actor(id="test-actor", label="test")


def _build_uow() -> tuple[fakes.FakeUnitOfWork, stock_fakes.FakeStockRepository]:
    repos: dict[type[aggregates.AggregateRoot[Any]], Any] = {}
    uow = fakes.FakeUnitOfWork(repos=repos)
    stock_repo = stock_fakes.FakeStockRepository(outbox=uow.outbox)
    repos[aggregate.Stock] = stock_repo
    return uow, stock_repo


def _create_stock(uow: fakes.FakeUnitOfWork, *, initial_quantity: int = 10) -> dto.StockOutputDTO:
    return stock.create_stock(
        uow=uow,
        input_dto=dto.CreateStockInputDTO(sku=_SKU.value, initial_quantity=initial_quantity),
        actor=_ACTOR,
    )


def test_create_stock() -> None:
    uow, _ = _build_uow()

    created = _create_stock(uow, initial_quantity=10)

    assert created.sku == _SKU.value
    assert created.available_quantity == 10
    assert uow.outbox.recorded  # StockCreated drained through the fake repo's add()
    assert uow.audit.entries


def test_reserve_within_available_quantity() -> None:
    uow, stock_repo = _build_uow()
    _create_stock(uow, initial_quantity=10)

    stock.reserve_stock(uow=uow, sku=_SKU, quantity=4, actor=_ACTOR)

    assert stock_repo.get_by_sku(_SKU).available_quantity == 6


def test_reserve_more_than_available_raises_and_leaves_stock_unchanged() -> None:
    uow, stock_repo = _build_uow()
    _create_stock(uow, initial_quantity=5)

    with pytest.raises(exceptions.InsufficientStockError):
        stock.reserve_stock(uow=uow, sku=_SKU, quantity=6, actor=_ACTOR)

    # The original exception type propagates unchanged through services/stock.py's
    # try/except Exception: ... raise, and the guard in Stock.reserve() runs before any
    # mutation — no partial decrement on a failed reservation.
    assert stock_repo.get_by_sku(_SKU).available_quantity == 5


def test_release_increases_available_quantity() -> None:
    uow, stock_repo = _build_uow()
    _create_stock(uow, initial_quantity=10)
    stock.reserve_stock(uow=uow, sku=_SKU, quantity=4, actor=_ACTOR)

    stock.release_stock(uow=uow, sku=_SKU, quantity=4, actor=_ACTOR)

    assert stock_repo.get_by_sku(_SKU).available_quantity == 10


def test_release_more_than_was_reserved_still_succeeds() -> None:
    """`Stock` (domain/model/aggregate.py) tracks only `available_quantity`, not a separate
    reserved pool — `release()` has no upper-bound guard, unlike `reserve()`'s
    `InsufficientStockError` check. Releasing more than was ever reserved is therefore not a
    domain error today; this test documents that real behavior rather than assuming a rule
    the aggregate doesn't actually enforce."""
    uow, stock_repo = _build_uow()
    _create_stock(uow, initial_quantity=10)
    stock.reserve_stock(uow=uow, sku=_SKU, quantity=2, actor=_ACTOR)

    stock.release_stock(uow=uow, sku=_SKU, quantity=100, actor=_ACTOR)

    assert stock_repo.get_by_sku(_SKU).available_quantity == 108
