import decimal
from typing import Self

from backend.commerce.orders.domain.model import events, exceptions, value_objects
from backend.commons.domain import aggregates, money
from backend.commons.domain import value_objects as base_value_objects

# Allowed status transitions — ARCHITECTURE.md §5.1a, the same shape as bold's
# `_BANCOLOMBIA_CARDLESS_CASHOUT_STATUS_TRANSITIONS`: a status maps to the list of statuses
# it may move to next. A PENDING order can cancel directly (never reserved stock, nothing
# to release); a CONFIRMED one can only move to CANCELLED (never back to PENDING).
_ORDER_STATUS_TRANSITIONS: dict[value_objects.OrderStatus, list[value_objects.OrderStatus]] = {
    value_objects.OrderStatus.PENDING: [
        value_objects.OrderStatus.CONFIRMED,
        value_objects.OrderStatus.CANCELLED,
    ],
    value_objects.OrderStatus.CONFIRMED: [value_objects.OrderStatus.CANCELLED],
    value_objects.OrderStatus.CANCELLED: [],
}


class Order(aggregates.AggregateRoot[value_objects.OrderId]):
    customer_id: value_objects.CustomerId
    lines: list[value_objects.OrderLine]
    status: value_objects.OrderStatus
    # Populated by confirm() only — a PENDING order hasn't been confirmed yet, so there's
    # nothing to ship (ARCHITECTURE.md §9.2's profile snapshot happens at confirm time).
    shipping_name: str | None = None
    shipping_email: str | None = None

    @classmethod
    def create(
        cls, *, customer_id: value_objects.CustomerId, lines: list[value_objects.OrderLine]
    ) -> Self:
        if not lines:
            raise exceptions.OrderMustHaveAtLeastOneLineError()
        now = base_value_objects.PosixTime.now()
        order = cls(
            id=value_objects.OrderId.new(),
            customer_id=customer_id,
            lines=lines,
            status=value_objects.OrderStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        order.record_event(events.OrderCreated(order_id=order.id, customer_id=customer_id))
        return order

    @property
    def total(self) -> money.Money:
        line_totals = (line.unit_price * line.quantity for line in self.lines)
        zero = money.Money(currency=self.lines[0].unit_price.currency, value=decimal.Decimal(0))
        return sum(line_totals, start=zero)

    @property
    def had_reserved_stock(self) -> bool:
        """Tell-Don't-Ask: CONFIRMED is the only status that implies stock was ever reserved
        (ARCHITECTURE.md §10.4's Order+Stock asymmetry — confirm_order_orchestrator is the
        only path that reserves it). A caller deciding whether to release stock asks this,
        instead of comparing `self.status` against a string itself. Must be read BEFORE
        `cancel()` — cancelling changes `self.status` to CANCELLED, so checking this
        afterward would always read False."""
        return self.status is value_objects.OrderStatus.CONFIRMED

    def confirm(self, *, shipping_name: str, shipping_email: str) -> None:
        self._transition_status(
            new_status=value_objects.OrderStatus.CONFIRMED,
            invalid_transition_error=exceptions.OrderCannotBeConfirmedError(
                order_id=self.id, status=self.status
            ),
        )
        self.shipping_name = shipping_name
        self.shipping_email = shipping_email
        self.record_event(events.OrderConfirmed(order_id=self.id))

    def cancel(self) -> None:
        previous_status = self.status
        self._transition_status(
            new_status=value_objects.OrderStatus.CANCELLED,
            invalid_transition_error=exceptions.OrderCannotBeCancelledError(
                order_id=self.id, status=self.status
            ),
        )
        self.record_event(
            events.OrderCancelled(
                order_id=self.id, lines=self.lines, previous_status=previous_status
            )
        )

    def _transition_status(
        self,
        *,
        new_status: value_objects.OrderStatus,
        invalid_transition_error: exceptions.OrderCannotBeConfirmedError
        | exceptions.OrderCannotBeCancelledError,
    ) -> None:
        """Single choke point for every status change — ARCHITECTURE.md §5.1a. The caller
        supplies its own named exception (bold's `_change_status` raises one generic
        `*UpdateStatusError` instead; this codebase keeps per-action exceptions so the
        `code` an API consumer sees stays action-specific, per §13) so the transition table
        stays the only thing this method owns."""
        if new_status not in _ORDER_STATUS_TRANSITIONS[self.status]:
            raise invalid_transition_error
        self.status = new_status
        self.touch()
