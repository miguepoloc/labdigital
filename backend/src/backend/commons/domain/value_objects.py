"""Base value objects shared across every bounded context — ARCHITECTURE.md §5.1/§5.2."""

import datetime
import secrets
import string
from typing import Self
import uuid

import uuid_extensions

from backend.commons.domain import base_model

_HUMAN_FRIENDLY_ALPHABET = string.ascii_uppercase + string.digits
_HUMAN_FRIENDLY_LENGTH = 10
_MICROSECONDS_PER_SECOND = 1_000_000


class ValueObject(base_model.DomainModel):
    """Immutable, defined by its value — never has an id."""

    model_config = {"frozen": True}


class PosixTime(ValueObject):
    """POSIX timestamp in integer microseconds since epoch, UTC.

    Never store or pass a native `datetime` across a domain boundary (ARCHITECTURE.md §1.8).
    Use these comparison operators — never unwrap `.microseconds` to compare by hand
    (§1.11/§20): that reimplements behavior this value object already provides correctly.
    """

    microseconds: int

    @classmethod
    def now(cls) -> "PosixTime":
        return cls.from_datetime(datetime.datetime.now(tz=datetime.UTC))

    @classmethod
    def from_datetime(cls, value: datetime.datetime) -> "PosixTime":
        return cls(microseconds=int(value.timestamp() * _MICROSECONDS_PER_SECOND))

    def to_datetime(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(
            self.microseconds / _MICROSECONDS_PER_SECOND, tz=datetime.UTC
        )

    def __lt__(self, other: "PosixTime") -> bool:
        return self.microseconds < other.microseconds

    def __le__(self, other: "PosixTime") -> bool:
        return self.microseconds <= other.microseconds

    def __gt__(self, other: "PosixTime") -> bool:
        return self.microseconds > other.microseconds

    def __ge__(self, other: "PosixTime") -> bool:
        return self.microseconds >= other.microseconds


class UuidV7Id(ValueObject):
    """Default typed-ID base. Time-ordered, good for B-tree indexes (ARCHITECTURE.md §5.2)."""

    value: uuid.UUID

    @classmethod
    def new(cls) -> Self:
        return cls(value=uuid_extensions.uuid7())

    def __str__(self) -> str:
        return str(self.value)


class HumanFriendlyId(ValueObject):
    """Use only when the ID is user-facing (appears in a URL, a support ticket)."""

    value: str

    @classmethod
    def new(cls) -> Self:
        alphabet = _HUMAN_FRIENDLY_ALPHABET
        generated = "".join(secrets.choice(alphabet) for _ in range(_HUMAN_FRIENDLY_LENGTH))
        return cls(value=generated)

    def __str__(self) -> str:
        return self.value
