"""Application layer for commerce/stock — ARCHITECTURE.md §6. The only module allowed to
call `uow.repo(aggregate.Stock)` or a Stock command method. No `_publish_events()` helper
here — `DefaultStockRepository.add`/`.update` do that internally (ARCHITECTURE.md §7/§11.2)."""

import typing

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.stock.adapters import repository
from backend.commerce.stock.domain.model import aggregate, exceptions, value_objects
from backend.commerce.stock.services import dto
from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import audit

_LOGGER = logs.get_logger()


def create_stock(
    *, uow: unit_of_work.UnitOfWork, input_dto: dto.CreateStockInputDTO, actor: audit.Actor
) -> dto.StockOutputDTO:
    with uow.transaction():
        stock = aggregate.Stock.create(
            sku=commerce_value_objects.Sku(value=input_dto.sku),
            initial_quantity=input_dto.initial_quantity,
        )
        _stock_repo(uow).add(stock)
        uow.audit.add(
            audit.AuditEntry(
                actor=actor,
                action=value_objects.AuditAction.CREATED,
                aggregate_type=value_objects.AuditAggregateType.STOCK,
                aggregate_id=str(stock.id),
            )
        )
    _LOGGER.info("Stock created for sku [%s]", stock.sku)
    return dto.StockOutputDTO.from_entity(stock)


def reserve_stock(
    *,
    uow: unit_of_work.UnitOfWork,
    sku: commerce_value_objects.Sku,
    quantity: int,
    actor: audit.Actor,
) -> None:
    with uow.transaction():
        stock_repo = _stock_repo(uow)  # must resolve inside transaction() — see orders.py's
        # identical note on _order_repo.
        stock = stock_repo.get_by_sku(sku)
        try:
            stock.reserve(quantity)
        except exceptions.InsufficientStockError:
            _LOGGER.exception("Failed to reserve %s unit(s) of sku [%s]", quantity, sku)
            raise
        stock_repo.update(stock)
        uow.audit.add(
            audit.AuditEntry(
                actor=actor,
                action=value_objects.AuditAction.RESERVED,
                aggregate_type=value_objects.AuditAggregateType.STOCK,
                aggregate_id=str(stock.id),
                changes={"quantity": quantity},
            )
        )
    _LOGGER.info("Reserved %s unit(s) of sku [%s]", quantity, sku)


def release_stock(
    *,
    uow: unit_of_work.UnitOfWork,
    sku: commerce_value_objects.Sku,
    quantity: int,
    actor: audit.Actor,
) -> None:
    with uow.transaction():
        stock_repo = _stock_repo(uow)
        stock = stock_repo.get_by_sku(sku)
        stock.release(quantity)  # never raises — Stock.release has no invalid-state check
        stock_repo.update(stock)
        uow.audit.add(
            audit.AuditEntry(
                actor=actor,
                action=value_objects.AuditAction.RELEASED,
                aggregate_type=value_objects.AuditAggregateType.STOCK,
                aggregate_id=str(stock.id),
                changes={"quantity": quantity},
            )
        )
    _LOGGER.info("Released %s unit(s) of sku [%s]", quantity, sku)


def get_stock_by_sku(
    *, uow: unit_of_work.UnitOfWork, sku: commerce_value_objects.Sku
) -> dto.StockOutputDTO:
    with uow.transaction():
        stock = _stock_repo(uow).get_by_sku(sku)
    return dto.StockOutputDTO.from_entity(stock)


def _stock_repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultStockRepository:
    """`uow.repo(...)` returns the generic Repository[T] port, which has no `get_by_sku`
    (bespoke queries stay off the generic interface, ARCHITECTURE.md §7). Explicit,
    visible cast — not a silent `# type: ignore`. Called once per function and reused for
    every subsequent repo call in it — see the identical note on orders.py's `_order_repo`."""
    return typing.cast(repository.DefaultStockRepository, uow.repo(aggregate.Stock))
