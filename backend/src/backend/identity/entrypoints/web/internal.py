"""Service-to-service only — ARCHITECTURE.md §9.2. Exists for exactly one reason: another
bounded context needs a point-in-time snapshot of data it must own a copy of. Never accepts
a customer JWT — `require_service_auth` is a different dependency entirely."""

from typing import Annotated

import fastapi
import mangum

from backend.commons.adapters import unit_of_work
from backend.commons.adapters.api import exception_handler, middleware
from backend.identity.entrypoints.web import _dependencies
from backend.identity.users.domain.model import value_objects
from backend.identity.users.services import auth, dto

app = fastapi.FastAPI(
    title="Identity — Internal API",
    dependencies=[fastapi.Depends(_dependencies.require_service_auth)],
)
app.add_middleware(middleware.RequestLoggingMiddleware)
exception_handler.install(app)

UowDep = Annotated[unit_of_work.UnitOfWork, fastapi.Depends(_dependencies.get_uow)]


@app.get("/internal/users/{user_id}/profile", response_model=dto.UserProfileOutputDTO)
def get_user_profile(user_id: str, uow: UowDep) -> dto.UserProfileOutputDTO:
    return auth.get_user_profile(uow=uow, user_id=value_objects.UserId(value=user_id))


handler = mangum.Mangum(app)
