from typing import Self

from backend.commerce.stock.domain.model import aggregate
from backend.commons.application import dto


class CreateStockInputDTO(dto.BaseDTO):
    sku: str
    initial_quantity: int


class StockOutputDTO(dto.BaseDTO):
    id: str
    sku: str
    available_quantity: int

    @classmethod
    def from_entity(cls, stock: aggregate.Stock) -> Self:
        return cls(
            id=str(stock.id), sku=stock.sku.value, available_quantity=stock.available_quantity
        )
