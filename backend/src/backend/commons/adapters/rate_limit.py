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
from backend.commons.domain import exceptions, rate_limits, value_objects


class RateLimitRepository:
    def __init__(self, session: orm.Session) -> None:
        self._session = session

    def hit(self, rule: rate_limits.RateLimitRule, key: str) -> None:
        """Cuenta un intento; lanza `TooManyRequestsError` si supera el límite."""
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
            raise exceptions.TooManyRequestsError(
                retry_after_seconds=max(1, window_start + window - now_seconds)
            )

    def prune(self) -> int:
        now_seconds = value_objects.PosixTime.now().microseconds // 1_000_000
        result = self._session.execute(
            sa.delete(orm_base.RateLimitOrm).where(orm_base.RateLimitOrm.expires_at < now_seconds)
        )
        return int(getattr(result, "rowcount", 0) or 0)
