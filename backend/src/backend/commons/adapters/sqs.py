"""Shared SQS event-consumer dispatcher — ARCHITECTURE.md §9.4. Ported from `bold`'s
type(event) -> handler strategy-map dispatch, with one improvement neither `bold` nor
`sona` has: idempotency is wrapped by the dispatcher itself for the common case, so a new
handler can't forget it."""

from collections.abc import Callable
import dataclasses
from typing import Any

from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import events, exceptions

_LOGGER = logs.get_logger()


@dataclasses.dataclass(frozen=True)
class EventConsumer[EventT: events.DomainEvent]:
    """One registered (event type, handler) pair — the single place that names both.

    A plain dataclass, not a ValueObject/Pydantic model (ARCHITECTURE.md §17.3): this holds
    a `type` and a `Callable`, constructed once in Python code at import time, never parsed
    from JSON or any other external input.

    Exactly one of `handle`/`handle_without_uow` must be set:
    - `handle` — the default: auto-wrapped in an idempotency-guarded transaction.
    - `handle_without_uow` — for the rare case a handler needs I/O before it knows what to
      write (§9.4's documented escape hatch).

    Two separate fields, not one `Callable[[UoW, EventT], None] | Callable[[EventT], None]`
    union dispatched by inspecting `len(inspect.signature(...).parameters)` at runtime (an
    earlier draft of this module did exactly that): mypy cannot narrow a union of
    different-arity callables by a runtime arity check, so that version needed two
    `# type: ignore`s at the call sites. Two mutually-exclusive fields need none — each has
    one concrete, non-union callable type — and the registration call site states its intent
    directly (`handle=` vs `handle_without_uow=`) instead of mypy/the dispatcher inferring it
    from how many parameters a function happens to declare.
    """

    event_class: type[EventT]
    handle: Callable[[unit_of_work.UnitOfWork, EventT], None] | None = None
    handle_without_uow: Callable[[EventT], None] | None = None

    def __post_init__(self) -> None:
        if (self.handle is None) == (self.handle_without_uow is None):
            raise ValueError(
                "EventConsumer needs exactly one of handle/handle_without_uow, not both/neither."
            )


def process_sqs_event(
    *,
    event: dict[str, Any],
    consumers: list[EventConsumer[Any]],
    consumer_name: str,
    uow_factory: Callable[[], unit_of_work.UnitOfWork] = unit_of_work.build,
) -> None:
    by_type_name = {c.event_class.__name__: c for c in consumers}
    _LOGGER.info("%s - event received", consumer_name)

    for record in event.get("Records", []):
        body = record.get("body")
        if not body:
            _LOGGER.warning("Empty SQS message body")
            continue

        try:
            envelope = events.parse_envelope(body)
        except ValueError:
            _LOGGER.warning("Malformed SQS message body: %s", body)
            continue

        event_type_name = envelope.get("event_type")
        consumer = by_type_name.get(event_type_name) if isinstance(event_type_name, str) else None
        if consumer is None:
            _LOGGER.warning("Unknown event type: %s", event_type_name)
            continue

        parsed_event = consumer.event_class.model_validate(envelope)
        _dispatch(consumer, parsed_event, uow_factory, consumer_name)


def _dispatch(
    consumer: EventConsumer[Any],
    parsed_event: events.DomainEvent,
    uow_factory: Callable[[], unit_of_work.UnitOfWork],
    consumer_name: str,
) -> None:
    try:
        if consumer.handle is not None:
            uow = uow_factory()
            with uow.transaction(idempotency_key=parsed_event.idempotence_key()):
                consumer.handle(uow, parsed_event)
        else:
            assert consumer.handle_without_uow is not None  # __post_init__ guarantees this
            consumer.handle_without_uow(parsed_event)
    except exceptions.DuplicatedTransactionError:
        _LOGGER.info("%s already processed, skipping", parsed_event.idempotence_key())
    except Exception:
        _LOGGER.exception("%s - error handling %s", consumer_name, consumer.event_class.__name__)
        raise  # let SQS/Lambda's own retry + DLQ redrive take over — no local retry
