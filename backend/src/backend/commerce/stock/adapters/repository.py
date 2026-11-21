import sqlalchemy as sa
from sqlalchemy.orm import Session
import sqlalchemy.orm.exc

from backend.commerce.commons import value_objects as commerce_value_objects
from backend.commerce.stock.adapters import orm
from backend.commerce.stock.domain.model import aggregate, exceptions, value_objects
from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects


def _to_orm(stock: aggregate.Stock) -> orm.StockOrm:
    return orm.StockOrm(
        id=stock.id.value,
        sku=stock.sku.value,
        available_quantity=stock.available_quantity,
        created_at=stock.created_at.microseconds,
        updated_at=stock.updated_at.microseconds,
        version=stock.version,
    )


def _to_entity(stock_orm: orm.StockOrm) -> aggregate.Stock:
    return aggregate.Stock(
        id=value_objects.StockId(value=stock_orm.id),
        sku=commerce_value_objects.Sku(value=stock_orm.sku),
        available_quantity=stock_orm.available_quantity,
        created_at=base_value_objects.PosixTime(microseconds=stock_orm.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=stock_orm.updated_at),
        version=stock_orm.version,
    )


class DefaultStockRepository(repositories.Repository[aggregate.Stock]):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, id: value_objects.StockId) -> aggregate.Stock:  # noqa: A002
        stock_orm = self._session.get(orm.StockOrm, id.value)
        if stock_orm is None:
            raise exceptions.StockNotFoundError(sku=id)
        return _to_entity(stock_orm)

    def get_by_sku(self, sku: commerce_value_objects.Sku) -> aggregate.Stock:
        stmt = sa.select(orm.StockOrm).where(orm.StockOrm.sku == sku.value)
        stock_orm = self._session.execute(stmt).scalar_one_or_none()
        if stock_orm is None:
            raise exceptions.StockNotFoundError(sku=sku)
        return _to_entity(stock_orm)

    def add(self, stock: aggregate.Stock) -> None:
        # UuidV7Id-keyed, so no insert_with_id_retry needed (ARCHITECTURE.md §5.2) — that
        # helper is only for HumanFriendlyId-keyed aggregates, like commerce.orders.Order.
        self._session.add(_to_orm(stock))
        self._session.flush()
        repository_helpers.publish_events(self._session, stock)

    def update(self, stock: aggregate.Stock) -> None:
        self._session.merge(_to_orm(stock))
        try:
            self._session.flush()  # forces the version check now, not at commit time
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                f"Stock [{stock.id}] changed concurrently — reload and retry.",
                code="CONCURRENT_MODIFICATION",
            ) from exc
        repository_helpers.publish_events(self._session, stock)

    def delete(self, id: value_objects.StockId) -> None:  # noqa: A002
        stock_orm = self._session.get(orm.StockOrm, id.value)
        if stock_orm is not None:
            self._session.delete(stock_orm)


unit_of_work.register_repo(aggregate.Stock, DefaultStockRepository)
