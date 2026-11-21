"""Base Pydantic model shared by every domain object in this codebase."""

import json
from typing import Any, Self

import pydantic


class DomainModel(pydantic.BaseModel):
    """Base for every domain object (entities, aggregates, value objects, events).

    Not for DTOs — those extend `commons.application.dto.BaseDTO` instead, since a DTO
    validates data crossing an HTTP/wire boundary while a DomainModel never does (see
    ARCHITECTURE.md §17.3 on when to reach for Pydantic at all).
    """

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(data)

    @classmethod
    def from_json(cls, data: str) -> Self:
        return cls.model_validate(json.loads(data))
