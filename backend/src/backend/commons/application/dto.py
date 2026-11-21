"""Base DTO — for data crossing the HTTP/wire boundary. Deliberately separate from
commons.domain.base_model.DomainModel (ARCHITECTURE.md §17.3): a DTO's job is
serialization, a DomainModel's job is business meaning; conflating them lets an API
contract accidentally leak internal domain shape."""

import pydantic


class BaseDTO(pydantic.BaseModel):
    model_config = {"frozen": True}


class PaginatedResult[T](pydantic.BaseModel):
    items: list[T]
    next_cursor: str | None = None
