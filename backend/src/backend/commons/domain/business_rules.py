"""Named business rules — ARCHITECTURE.md §5.4. Use for an invariant complex enough to
deserve independent testing and a name; trivial invariants stay as an inline `if/raise`
inside the aggregate method."""

import abc

from backend.commons.domain import exceptions


class BusinessRule(abc.ABC):
    @abc.abstractmethod
    def is_broken(self) -> bool: ...

    @abc.abstractmethod
    def message(self) -> str: ...

    def check(self) -> None:
        if self.is_broken():
            raise exceptions.ValidationError(self.message(), code="BUSINESS_RULE_VIOLATION")
