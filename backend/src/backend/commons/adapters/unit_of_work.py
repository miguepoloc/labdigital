"""Generic Unit of Work — ARCHITECTURE.md §8/§8.1/§12. One class for the whole codebase;
no per-context subclasses. Resolves repositories by aggregate type via a registry populated
once at import time by each subcontext's adapters/repository.py."""

from collections.abc import Callable, Generator
import contextlib
from typing import Any

import sqlalchemy.exc
from sqlalchemy.orm import Session, sessionmaker

from backend.commons.adapters import audit as audit_module
from backend.commons.adapters import engine, orm_base
from backend.commons.adapters import outbox as outbox_module
from backend.commons.domain import aggregates, exceptions, repositories, value_objects

# A factory, not `type[Repository[Any]]` — the ABC (commons/domain/repositories.py)
# deliberately declares no `__init__`, so mypy has no way to know every concrete repository
# takes a `Session`. `Callable[[Session], Repository[Any]]` states the real contract
# directly: a concrete repository CLASS satisfies this by virtue of its own `__init__`
# matching, no `# type: ignore` needed at the call site below.
_REPO_REGISTRY: dict[
    type[aggregates.AggregateRoot[Any]], Callable[[Session], repositories.Repository[Any]]
] = {}


def register_repo(
    aggregate_type: type[aggregates.AggregateRoot[Any]],
    repo_factory: Callable[[Session], repositories.Repository[Any]],
) -> None:
    """Called once at import time by each subcontext's adapters/repository.py — passing the
    concrete repository class itself (e.g. `DefaultOrderRepository`), whose `__init__`
    matches this factory signature."""
    _REPO_REGISTRY[aggregate_type] = repo_factory


class UnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or engine.get_session_factory()
        self._session: Session | None = None
        self._repos: dict[type, repositories.Repository[Any]] = {}

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork.session accessed outside a transaction() block.")
        return self._session

    def repo[T: aggregates.AggregateRoot[Any]](
        self, aggregate_type: type[T]
    ) -> repositories.Repository[T]:
        if aggregate_type not in self._repos:
            repo_factory = _REPO_REGISTRY[aggregate_type]
            self._repos[aggregate_type] = repo_factory(self.session)
        return self._repos[aggregate_type]

    @property
    def outbox(self) -> outbox_module.OutboxRepository:
        return outbox_module.OutboxRepository(self.session)

    @property
    def audit(self) -> audit_module.AuditRepository:
        return audit_module.AuditRepository(self.session)

    @contextlib.contextmanager
    def transaction(self, *, idempotency_key: str | None = None) -> Generator[None]:
        if self._session is not None:
            # Nested call joins the outer transaction — no-op re-entrancy. This is the
            # mechanism that makes orchestrator-composed atomicity work (ARCHITECTURE.md
            # §8/§10.2): a product-level orchestrator opens the outer transaction() and each
            # service function's own transaction() call simply joins it.
            yield
            return
        self._session = self._session_factory()
        try:
            if idempotency_key is not None:
                self._claim_idempotency_key(idempotency_key)
            yield
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        finally:
            self._session.close()
            self._session = None
            self._repos.clear()

    def _claim_idempotency_key(self, key: str) -> None:
        """ARCHITECTURE.md §12.1/§12.2 — one mechanism, two call sites (a client's
        Idempotency-Key header, or an event's idempotence_key()). Flushed immediately so a
        duplicate is caught before any other work in this transaction runs."""
        self.session.add(
            orm_base.IdempotencyKeyOrm(
                key=key, created_at=value_objects.PosixTime.now().microseconds
            )
        )
        try:
            self.session.flush()
        except sqlalchemy.exc.IntegrityError as exc:
            raise exceptions.DuplicatedTransactionError(
                f"Request with idempotency key [{key}] was already processed.",
                code="DUPLICATED_TRANSACTION",
            ) from exc


def build() -> UnitOfWork:
    """Factory used by entrypoints (ARCHITECTURE.md §9.1/§9.4) — one call per request or
    per event-batch invocation."""
    return UnitOfWork()
