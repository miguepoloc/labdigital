import sqlalchemy as sa
from sqlalchemy import orm as sa_orm
import sqlalchemy.orm.exc

from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.sessions.adapters import orm
from backend.identity.sessions.domain.model import aggregate, exceptions, value_objects


def _posix(value: int | None) -> base_value_objects.PosixTime | None:
    return None if value is None else base_value_objects.PosixTime(microseconds=value)


def _record(row: orm.RefreshTokenOrm) -> value_objects.RefreshTokenRecord:
    return value_objects.RefreshTokenRecord(
        id=value_objects.RefreshTokenId(value=row.id),
        token_hash=row.token_hash,
        created_at=base_value_objects.PosixTime(microseconds=row.created_at),
        expires_at=base_value_objects.PosixTime(microseconds=row.expires_at),
        rotated_at=_posix(row.rotated_at),
    )


def _to_orm(session: aggregate.Session) -> orm.SessionOrm:
    return orm.SessionOrm(
        id=session.id.value,
        user_id=session.user_id.value,
        persistent=session.persistent,
        user_agent=session.user_agent,
        ip=session.ip,
        credentials_version=session.credentials_version,
        last_used_at=session.last_used_at.microseconds,
        expires_at=session.current_token.expires_at.microseconds,
        current_token_id=session.current_token.id.value,
        revoked_at=None if session.revoked_at is None else session.revoked_at.microseconds,
        revoke_reason=None if session.revoke_reason is None else session.revoke_reason.value,
        created_at=session.created_at.microseconds,
        updated_at=session.updated_at.microseconds,
        version=session.version,
    )


def _to_entity(row: orm.SessionOrm, current: orm.RefreshTokenOrm) -> aggregate.Session:
    return aggregate.Session(
        id=value_objects.SessionId(value=row.id),
        user_id=identity_value_objects.UserId(value=row.user_id),
        persistent=row.persistent,
        user_agent=row.user_agent,
        ip=row.ip,
        credentials_version=row.credentials_version,
        last_used_at=base_value_objects.PosixTime(microseconds=row.last_used_at),
        revoked_at=_posix(row.revoked_at),
        revoke_reason=None
        if row.revoke_reason is None
        else value_objects.RevokeReason(row.revoke_reason),
        current_token=_record(current),
        created_at=base_value_objects.PosixTime(microseconds=row.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=row.updated_at),
        version=row.version,
    )


class DefaultSessionRepository(repositories.Repository[aggregate.Session]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: value_objects.SessionId) -> aggregate.Session:  # noqa: A002
        row = self._session.get(orm.SessionOrm, id.value, with_for_update=True)
        if row is None:
            raise exceptions.SessionNotFoundError()
        return self._load(row)

    def find(self, id: value_objects.SessionId) -> aggregate.Session | None:  # noqa: A002
        """Lectura SIN bloqueo (comprobación de vida en cada petición)."""
        row = self._session.get(orm.SessionOrm, id.value)
        return None if row is None else self._load(row)

    def find_by_token_id(
        self, token_id: value_objects.RefreshTokenId
    ) -> tuple[aggregate.Session, value_objects.RefreshTokenRecord] | None:
        """Devuelve la sesión (bloqueada `FOR UPDATE`: dos canjes simultáneos del mismo
        token se serializan y el segundo ve el token ya rotado ⇒ reuso) y el eslabón
        presentado."""
        token_row = self._session.get(orm.RefreshTokenOrm, token_id.value)
        if token_row is None:
            return None
        row = self._session.get(orm.SessionOrm, token_row.session_id, with_for_update=True)
        if row is None:
            return None
        self._session.refresh(token_row)  # releer tras obtener el bloqueo
        return self._load(row), _record(token_row)

    def list_active_for_user(
        self, user_id: identity_value_objects.UserId
    ) -> list[aggregate.Session]:
        now = base_value_objects.PosixTime.now().microseconds
        stmt = (
            sa.select(orm.SessionOrm)
            .where(
                orm.SessionOrm.user_id == user_id.value,
                orm.SessionOrm.revoked_at.is_(None),
                orm.SessionOrm.expires_at > now,
            )
            .order_by(orm.SessionOrm.last_used_at.desc())
        )
        return [self._load(row) for row in self._session.scalars(stmt)]

    def delete_expired(self, *, older_than: base_value_objects.PosixTime) -> int:
        """Housekeeping: borra sesiones caducadas o revocadas antes de `older_than` (sus
        refresh tokens caen por `ON DELETE CASCADE`)."""
        cutoff = older_than.microseconds
        result = self._session.execute(
            sa.delete(orm.SessionOrm).where(
                sa.or_(orm.SessionOrm.expires_at < cutoff, orm.SessionOrm.revoked_at < cutoff)
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def add(self, session: aggregate.Session) -> None:
        self._session.add(_to_orm(session))
        self._session.flush()
        self._session.add(_token_row(session))
        self._session.flush()
        repository_helpers.publish_events(self._session, session)

    def update(self, session: aggregate.Session) -> None:
        now = base_value_objects.PosixTime.now().microseconds
        self._session.merge(_to_orm(session))
        try:
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                "La sesión cambió a la vez en otra petición.", code="concurrent_modification"
            ) from exc
        current_id = session.current_token.id.value
        if self._session.get(orm.RefreshTokenOrm, current_id) is None:
            self._session.add(_token_row(session))
        self._session.execute(
            sa.update(orm.RefreshTokenOrm)
            .where(
                orm.RefreshTokenOrm.session_id == session.id.value,
                orm.RefreshTokenOrm.id != current_id,
                orm.RefreshTokenOrm.rotated_at.is_(None),
            )
            .values(rotated_at=now)
        )
        if session.is_revoked:
            self._session.execute(
                sa.update(orm.RefreshTokenOrm)
                .where(
                    orm.RefreshTokenOrm.session_id == session.id.value,
                    orm.RefreshTokenOrm.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
        self._session.flush()
        repository_helpers.publish_events(self._session, session)

    def delete(self, id: value_objects.SessionId) -> None:  # noqa: A002
        row = self._session.get(orm.SessionOrm, id.value)
        if row is not None:
            self._session.delete(row)

    def _load(self, row: orm.SessionOrm) -> aggregate.Session:
        current = self._session.get(orm.RefreshTokenOrm, row.current_token_id)
        if current is None:
            raise exceptions.SessionNotFoundError()
        return _to_entity(row, current)


def _token_row(session: aggregate.Session) -> orm.RefreshTokenOrm:
    record = session.current_token
    return orm.RefreshTokenOrm(
        id=record.id.value,
        session_id=session.id.value,
        token_hash=record.token_hash,
        created_at=record.created_at.microseconds,
        expires_at=record.expires_at.microseconds,
        rotated_at=None,
        revoked_at=None,
    )


unit_of_work.register_repo(aggregate.Session, DefaultSessionRepository)
