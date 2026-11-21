"""Rate limiting de ventana fija en Postgres — contrato §6 (`rate_limited` + `Retry-After`).

Elección: Postgres y no memoria del proceso, porque la API corre con varios workers de
uvicorn (cada uno con su memoria) y un reinicio no debe resetear los contadores. Un
`INSERT ... ON CONFLICT DO UPDATE ... RETURNING` es atómico, así que no hay carreras entre
peticiones concurrentes. Coste: una escritura por intento en los endpoints limitados
(login/registro/recuperación), despreciable para este tráfico.

Se llama en su PROPIA transacción, antes de la del caso de uso: si el caso de uso falla
(contraseña incorrecta) y hace rollback, el intento debe quedar contado igualmente.
"""

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql

from backend.commons.adapters import orm_base
from backend.commons.domain import rate_limits, value_objects


def _now_seconds() -> int:
    return value_objects.PosixTime.now().microseconds // 1_000_000


class RateLimitRepository:
    def __init__(self, session: orm.Session) -> None:
        self._session = session

    def hit(self, rule: rate_limits.RateLimitRule, key: str) -> int | None:
        """Cuenta un intento. Devuelve los segundos de `Retry-After` si se superó el límite
        (o `None`). No lanza: el llamador debe CONFIRMAR la transacción (para que el intento
        quede contado) y lanzar `TooManyRequestsError` después."""
        now_seconds = value_objects.PosixTime.now().microseconds // 1_000_000
        window = rule.window_seconds
        window_start = now_seconds - now_seconds % window
        bucket = f"{rule.name}:{key}"
        stmt = (
            postgresql.insert(orm_base.RateLimitOrm)
            .values(
                bucket=bucket, window_start=window_start, hits=1, expires_at=window_start + window
            )
            .on_conflict_do_update(
                index_elements=["bucket", "window_start"],
                set_={"hits": orm_base.RateLimitOrm.hits + 1},
            )
            .returning(orm_base.RateLimitOrm.hits)
        )
        hits = self._session.execute(stmt).scalar_one()
        if hits > rule.limit:
            return max(1, window_start + window - now_seconds)
        return None

    def prune(self) -> int:
        now_seconds = value_objects.PosixTime.now().microseconds // 1_000_000
        result = self._session.execute(
            sa.delete(orm_base.RateLimitOrm).where(orm_base.RateLimitOrm.expires_at < now_seconds)
        )
        return int(getattr(result, "rowcount", 0) or 0)


class BackoffRepository:
    """Retardo creciente tras fallos consecutivos (`rate_limits.BackoffRule`). Igual que
    `RateLimitRepository`: Postgres (global a los workers de uvicorn) y transacción PROPIA,
    para que el fallo quede registrado aunque el caso de uso haga rollback."""

    def __init__(self, session: orm.Session) -> None:
        self._session = session

    def retry_after(self, rule: rate_limits.BackoffRule, key: str) -> int | None:
        """Segundos que faltan para poder reintentar, o `None` si no hay bloqueo."""
        blocked_until = self._session.execute(
            sa.select(orm_base.BackoffCounterOrm.blocked_until).where(
                orm_base.BackoffCounterOrm.bucket == _bucket(rule, key)
            )
        ).scalar_one_or_none()
        now = _now_seconds()
        if blocked_until is None or blocked_until <= now:
            return None
        return blocked_until - now

    def record_failure(self, rule: rate_limits.BackoffRule, key: str) -> int:
        """Suma un fallo (o reinicia la cuenta si el último fue hace más de
        `reset_after_seconds`) y fija el bloqueo. Devuelve el retardo impuesto (0 = ninguno).
        `SELECT ... FOR UPDATE` tras un `INSERT ... ON CONFLICT DO NOTHING`: dos fallos
        simultáneos se serializan y ambos cuentan."""
        bucket = _bucket(rule, key)
        now = _now_seconds()
        self._session.execute(
            postgresql.insert(orm_base.BackoffCounterOrm)
            .values(bucket=bucket, failures=0, last_failure_at=now, blocked_until=0)
            .on_conflict_do_nothing(index_elements=["bucket"])
        )
        row = self._session.execute(
            sa.select(orm_base.BackoffCounterOrm)
            .where(orm_base.BackoffCounterOrm.bucket == bucket)
            .with_for_update()
        ).scalar_one()
        stale = now - row.last_failure_at > rule.reset_after_seconds
        row.failures = 1 if stale else row.failures + 1
        row.last_failure_at = now
        delay = rule.delay_after(row.failures)
        row.blocked_until = now + delay
        self._session.flush()
        return delay

    def reset(self, rule: rate_limits.BackoffRule, key: str) -> None:
        self._session.execute(
            sa.delete(orm_base.BackoffCounterOrm).where(
                orm_base.BackoffCounterOrm.bucket == _bucket(rule, key)
            )
        )

    def prune(self, *, older_than_seconds: int = 86_400) -> int:
        cutoff = _now_seconds() - older_than_seconds
        result = self._session.execute(
            sa.delete(orm_base.BackoffCounterOrm).where(
                orm_base.BackoffCounterOrm.last_failure_at < cutoff,
                orm_base.BackoffCounterOrm.blocked_until < _now_seconds(),
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)


def _bucket(rule: rate_limits.BackoffRule, key: str) -> str:
    return f"{rule.name}:{key}"
