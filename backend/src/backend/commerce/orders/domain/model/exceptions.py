from backend.commons.domain import exceptions


class OrderNotFoundError(exceptions.NotFoundError):
    def __init__(self, *, order_id: object) -> None:
        super().__init__(f"Order [{order_id}] not found.", code="ORDER_NOT_FOUND")


class OrderMustHaveAtLeastOneLineError(exceptions.ValidationError):
    def __init__(self) -> None:
        super().__init__("An order must have at least one line.", code="ORDER_EMPTY")


class OrderCannotBeConfirmedError(exceptions.ConflictError):
    def __init__(self, *, order_id: object, status: object) -> None:
        super().__init__(
            f"Order [{order_id}] cannot be confirmed from status [{status}].",
            code="ORDER_CANNOT_BE_CONFIRMED",
        )


class OrderCannotBeCancelledError(exceptions.ConflictError):
    def __init__(self, *, order_id: object, status: object) -> None:
        super().__init__(
            f"Order [{order_id}] cannot be cancelled from status [{status}].",
            code="ORDER_CANNOT_BE_CANCELLED",
        )
