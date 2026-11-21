"""Shared `StrEnum` base classes — ARCHITECTURE.md §17.3.

`enum.StrEnum` already overrides `_generate_next_value_` to lowercase the member name for
`enum.auto()` — plain `enum.StrEnum` is the right base whenever that's the value you want
(`OrderStatus.PENDING = enum.auto()` → `"pending"`). `UpperStrEnum` below is the other half:
the same `auto()` convenience for enums whose value must be the member name unchanged
(uppercase, since Python enum members are conventionally written uppercase) — ISO-4217
currency codes, unit codes, anything where lowercasing would silently produce the wrong
value. Pick the base by what the value actually needs to be; there's no default that's
"more correct" than the other.
"""

import enum


class UpperStrEnum(enum.StrEnum):
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str:
        return name
