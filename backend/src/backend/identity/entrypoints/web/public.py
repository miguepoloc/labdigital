"""One Lambda, multiple routes — ARCHITECTURE.md §9.1. Customer-facing; JWT required by
default, `/register`/`/login`/`/refresh` are the explicit exemptions."""

from typing import Annotated

import fastapi
from fastapi import status
import mangum

from backend.commons.adapters import unit_of_work
from backend.commons.adapters.api import exception_handler, middleware
from backend.identity.entrypoints.web import _dependencies
from backend.identity.users.domain.model import value_objects
from backend.identity.users.services import auth, dto

app = fastapi.FastAPI(title="Identity — Users API")
app.add_middleware(middleware.RequestLoggingMiddleware)
exception_handler.install(app)

UowDep = Annotated[unit_of_work.UnitOfWork, fastapi.Depends(_dependencies.get_uow)]


@app.post("/users/register", response_model=dto.UserOutputDTO, status_code=status.HTTP_201_CREATED)
def register_user(body: dto.RegisterUserInputDTO, uow: UowDep) -> dto.UserOutputDTO:
    return auth.register_user(uow=uow, input_dto=body)


@app.post("/users/login", response_model=dto.TokenPairOutputDTO)
def login(body: dto.LoginInputDTO, uow: UowDep) -> dto.TokenPairOutputDTO:
    return auth.login(uow=uow, input_dto=body)


@app.post("/users/refresh", response_model=dto.TokenPairOutputDTO)
def refresh(body: dto.RefreshInputDTO, uow: UowDep) -> dto.TokenPairOutputDTO:
    return auth.refresh(uow=uow, input_dto=body)


@app.post("/users/me/deactivate", response_model=dto.UserOutputDTO)
def deactivate_me(
    uow: UowDep,
    user_id: Annotated[value_objects.UserId, fastapi.Depends(_dependencies.require_jwt)],
) -> dto.UserOutputDTO:
    # Single-aggregate use case (ARCHITECTURE.md §10.1) — commerce reacts asynchronously via
    # the outbox-published UserDeactivated event (§10.3/§11), not a second call here.
    return auth.deactivate_user(
        uow=uow, input_dto=dto.DeactivateUserInputDTO(user_id=user_id.value)
    )


handler = mangum.Mangum(app)
