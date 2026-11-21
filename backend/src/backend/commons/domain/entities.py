"""Base Entity — ARCHITECTURE.md §5.1."""

from backend.commons.domain import base_model, value_objects


class Entity[IdT](base_model.DomainModel):
    id: IdT
    created_at: value_objects.PosixTime
    updated_at: value_objects.PosixTime

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.id == other.id

    def __hash__(self) -> int:
        return hash((type(self), self.id))
