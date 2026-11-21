"""Money value object — ARCHITECTURE.md §5.7, ported (trimmed) from bold's real
`commons.standard_types.money`. Every operation a caller could plausibly need lives here,
so no caller anywhere ever reaches into `.value`/`.currency` to reimplement one by hand
(§1.11's Law-of-Demeter rule)."""

import decimal
import enum

import pydantic

from backend.commons.domain import enums, exceptions, value_objects


class Currencies(enums.UpperStrEnum):
    # UpperStrEnum, not plain enum.StrEnum (contrast commerce.orders...OrderStatus) — ISO-4217
    # codes are uppercase, and plain StrEnum's auto() would lowercase the member name to "cop".
    COP = enum.auto()
    USD = enum.auto()
    # Trim to the currencies your product actually needs; see bold's original for the
    # full ISO-4217 set if you need more.


class Money(value_objects.ValueObject):
    currency: Currencies
    value: decimal.Decimal

    def __add__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(currency=self.currency, value=self.value + other.value)

    def __sub__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(currency=self.currency, value=self.value - other.value)

    def __mul__(self, other: int | decimal.Decimal) -> "Money":
        return Money(currency=self.currency, value=self.value * decimal.Decimal(other))

    def __neg__(self) -> "Money":
        return Money(currency=self.currency, value=-self.value)

    def __abs__(self) -> "Money":
        return Money(currency=self.currency, value=abs(self.value))

    def __str__(self) -> str:
        return f"{self.value:,.2f} {self.currency}"

    def compare(self, other: "Money") -> decimal.Decimal:
        self._check_currency(other)
        return self.value.compare(other.value)

    def __lt__(self, other: "Money") -> bool:
        return self.compare(other) < 0

    def __le__(self, other: "Money") -> bool:
        return self.compare(other) <= 0

    def __gt__(self, other: "Money") -> bool:
        return self.compare(other) > 0

    def __ge__(self, other: "Money") -> bool:
        return self.compare(other) >= 0

    def is_zero(self) -> bool:
        return self.value.is_zero()

    def _check_currency(self, other: "Money") -> None:
        if self.currency is not other.currency:
            raise exceptions.ValidationError(
                f"Can't operate on Money in different currencies: "
                f"[{self.currency}] vs [{other.currency}].",
                code="CURRENCY_MISMATCH",
            )

    @classmethod
    def cop(cls, value: decimal.Decimal) -> "Money":
        return cls(currency=Currencies.COP, value=value)

    @classmethod
    def zero(cls, currency: Currencies) -> "Money":
        return cls(currency=currency, value=decimal.Decimal(0))


class NonNegativeMoney(Money):
    """Does not accept negative values (e.g. an account balance)."""

    value: decimal.Decimal = pydantic.Field(ge=0)


class PositiveMoney(Money):
    """Does not accept negative or zero values (e.g. an order line's unit price)."""

    value: decimal.Decimal = pydantic.Field(gt=0)
