from backend.commons.domain import exceptions


class StockNotFoundError(exceptions.NotFoundError):
    def __init__(self, *, sku: object) -> None:
        super().__init__(f"Stock for sku [{sku}] not found.", code="STOCK_NOT_FOUND")


class InsufficientStockError(exceptions.ConflictError):
    def __init__(self, *, sku: object, requested: int, available: int) -> None:
        super().__init__(
            f"Cannot reserve {requested} of sku [{sku}]: only {available} available.",
            code="INSUFFICIENT_STOCK",
        )
