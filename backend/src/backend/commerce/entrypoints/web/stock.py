"""StockLambda — ARCHITECTURE.md §9.1. An internal/ops concern in a real system (behind
its own service-to-service auth, the same shape as `identity.entrypoints.web.internal`) —
kept behind the same JWT check as `orders.py` here for the golden path's simplicity; see
the README for where to split the auth model too, not just the router.

Split from `orders.py` because orders and stock are independent bounded contexts
(ARCHITECTURE.md §10.4) — see `orders.py`'s docstring for the sona-sso-backend precedent."""

from typing import Annotated

import fastapi
from fastapi import status
import mangum

from backend.commerce.entrypoints.web import _dependencies
from backend.commerce.stock.services import dto as stock_dto
from backend.commerce.stock.services import stock
from backend.commons.adapters import authentication, unit_of_work
from backend.commons.adapters.api import exception_handler, middleware
from backend.commons.domain import audit

app = fastapi.FastAPI(title="Commerce — Stock API")
app.add_middleware(middleware.RequestLoggingMiddleware)
exception_handler.install(app)

UowDep = Annotated[unit_of_work.UnitOfWork, fastapi.Depends(_dependencies.get_uow)]
UserDep = Annotated[authentication.AuthenticatedUser, fastapi.Depends(_dependencies.require_jwt)]


@app.post("/stock", response_model=stock_dto.StockOutputDTO, status_code=status.HTTP_201_CREATED)
def create_stock(
    body: stock_dto.CreateStockInputDTO, uow: UowDep, user: UserDep
) -> stock_dto.StockOutputDTO:
    return stock.create_stock(
        uow=uow, input_dto=body, actor=audit.Actor(id=user.user_id, label=user.user_id)
    )


handler = mangum.Mangum(app)
