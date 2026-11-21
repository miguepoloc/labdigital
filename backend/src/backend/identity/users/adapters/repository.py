import sqlalchemy as sa
from sqlalchemy import orm as sa_orm
import sqlalchemy.exc
import sqlalchemy.orm.exc

from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.users.adapters import orm
from backend.identity.users.domain.model import aggregate, exceptions, value_objects


def _posix(value: int | None) -> base_value_objects.PosixTime | None:
    return None if value is None else base_value_objects.PosixTime(microseconds=value)


def _micros(value: base_value_objects.PosixTime | None) -> int | None:
    return None if value is None else value.microseconds


def _to_orm(user: aggregate.User) -> orm.UserOrm:
    return orm.UserOrm(
        id=user.id.value,
        email=user.email.value,
        full_name=user.full_name.value,
        password_hash=user.hashed_password.encoded,
        role=user.role.value,
        email_verified_at=_micros(user.email_verified_at),
        credentials_version=user.credentials_version,
        is_active=user.is_active,
        data_policy_version=user.data_policy.version,
        data_policy_accepted_at=user.data_policy.accepted_at.microseconds,
        created_at=user.created_at.microseconds,
        updated_at=user.updated_at.microseconds,
        version=user.version,
    )


def _to_entity(row: orm.UserOrm) -> aggregate.User:
    return aggregate.User(
        id=identity_value_objects.UserId(value=row.id),
        email=value_objects.Email(value=row.email),
        full_name=value_objects.FullName(value=row.full_name),
        hashed_password=value_objects.HashedPassword(encoded=row.password_hash),
        role=identity_value_objects.Role(row.role),
        email_verified_at=_posix(row.email_verified_at),
        credentials_version=row.credentials_version,
        is_active=row.is_active,
        data_policy=value_objects.DataPolicyAcceptance(
            version=row.data_policy_version,
            accepted_at=base_value_objects.PosixTime(microseconds=row.data_policy_accepted_at),
        ),
        created_at=base_value_objects.PosixTime(microseconds=row.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=row.updated_at),
        version=row.version,
    )


class DefaultUserRepository(repositories.Repository[aggregate.User]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: identity_value_objects.UserId) -> aggregate.User:  # noqa: A002
        row = self._session.get(orm.UserOrm, id.value)
        if row is None:
            raise exceptions.UserNotFoundError(identifier=id)
        return _to_entity(row)

    def get_by_email(self, email: value_objects.Email) -> aggregate.User:
        stmt = sa.select(orm.UserOrm).where(orm.UserOrm.email == email.value)
        row = self._session.execute(stmt).scalar_one_or_none()
        if row is None:
            raise exceptions.UserNotFoundError(identifier=email)
        return _to_entity(row)

    def list_by_ids(self, ids: list[identity_value_objects.UserId]) -> list[aggregate.User]:
        if not ids:
            return []
        stmt = sa.select(orm.UserOrm).where(orm.UserOrm.id.in_([i.value for i in ids]))
        return [_to_entity(row) for row in self._session.scalars(stmt)]

    def search(self, query: str | None, *, limit: int, offset: int) -> list[aggregate.User]:
        """Por correo o nombre (subcadena, sin distinguir mayúsculas)."""
        stmt = sa.select(orm.UserOrm).order_by(orm.UserOrm.created_at.desc())
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            stmt = stmt.where(
                sa.or_(
                    orm.UserOrm.email.ilike(pattern, escape="\\"),
                    orm.UserOrm.full_name.ilike(pattern, escape="\\"),
                )
            )
        return [_to_entity(row) for row in self._session.scalars(stmt.limit(limit).offset(offset))]

    def add(self, user: aggregate.User) -> None:
        """UUIDv7: no hace falta `insert_with_id_retry`. Un correo duplicado (carrera entre
        dos registros simultáneos) se traduce a `UserAlreadyExistsError` dentro de un
        SAVEPOINT, sin romper la transacción exterior."""
        try:
            with self._session.begin_nested():
                self._session.add(_to_orm(user))
                self._session.flush()
        except sqlalchemy.exc.IntegrityError as exc:
            raise exceptions.UserAlreadyExistsError() from exc
        repository_helpers.publish_events(self._session, user)

    def update(self, user: aggregate.User) -> None:
        self._session.merge(_to_orm(user))
        try:
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                "El usuario cambió a la vez en otra petición; inténtalo de nuevo.",
                code="concurrent_modification",
            ) from exc
        repository_helpers.publish_events(self._session, user)

    def delete(self, id: identity_value_objects.UserId) -> None:  # noqa: A002
        row = self._session.get(orm.UserOrm, id.value)
        if row is not None:
            self._session.delete(row)


def _token_to_orm(token: aggregate.EmailToken) -> orm.EmailTokenOrm:
    return orm.EmailTokenOrm(
        id=token.id.value,
        user_id=token.user_id.value,
        purpose=token.purpose.value,
        token_hash=token.token_hash,
        expires_at=token.expires_at.microseconds,
        used_at=_micros(token.used_at),
        created_at=token.created_at.microseconds,
        updated_at=token.updated_at.microseconds,
    )


def _token_to_entity(row: orm.EmailTokenOrm) -> aggregate.EmailToken:
    return aggregate.EmailToken(
        id=value_objects.EmailTokenId(value=row.id),
        user_id=identity_value_objects.UserId(value=row.user_id),
        purpose=value_objects.EmailTokenPurpose(row.purpose),
        token_hash=row.token_hash,
        expires_at=base_value_objects.PosixTime(microseconds=row.expires_at),
        used_at=_posix(row.used_at),
        created_at=base_value_objects.PosixTime(microseconds=row.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=row.updated_at),
    )


class DefaultEmailTokenRepository(repositories.Repository[aggregate.EmailToken]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: value_objects.EmailTokenId) -> aggregate.EmailToken:  # noqa: A002
        row = self._session.get(orm.EmailTokenOrm, id.value)
        if row is None:
            raise exceptions.InvalidEmailTokenError()
        return _token_to_entity(row)

    def get_by_secret(
        self, secret: str, *, purpose: value_objects.EmailTokenPurpose
    ) -> aggregate.EmailToken:
        """Busca por hash; bloquea la fila (`FOR UPDATE`) para que dos usos simultáneos del
        mismo enlace no lo consuman ambos."""
        stmt = (
            sa.select(orm.EmailTokenOrm)
            .where(
                orm.EmailTokenOrm.token_hash == value_objects.hash_token_secret(secret),
                orm.EmailTokenOrm.purpose == purpose.value,
            )
            .with_for_update()
        )
        row = self._session.execute(stmt).scalar_one_or_none()
        if row is None:
            raise exceptions.InvalidEmailTokenError()
        return _token_to_entity(row)

    def invalidate_open(
        self, *, user_id: identity_value_objects.UserId, purpose: value_objects.EmailTokenPurpose
    ) -> None:
        """Marca como usados los tokens abiertos (al emitir uno nuevo, sólo vale el último)."""
        now = base_value_objects.PosixTime.now().microseconds
        self._session.execute(
            sa.update(orm.EmailTokenOrm)
            .where(
                orm.EmailTokenOrm.user_id == user_id.value,
                orm.EmailTokenOrm.purpose == purpose.value,
                orm.EmailTokenOrm.used_at.is_(None),
            )
            .values(used_at=now, updated_at=now)
        )

    def delete_expired(self, *, older_than: base_value_objects.PosixTime) -> int:
        result = self._session.execute(
            sa.delete(orm.EmailTokenOrm).where(
                orm.EmailTokenOrm.expires_at < older_than.microseconds
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def add(self, token: aggregate.EmailToken) -> None:
        self._session.add(_token_to_orm(token))
        self._session.flush()
        repository_helpers.publish_events(self._session, token)

    def update(self, token: aggregate.EmailToken) -> None:
        self._session.merge(_token_to_orm(token))
        self._session.flush()
        repository_helpers.publish_events(self._session, token)

    def delete(self, id: value_objects.EmailTokenId) -> None:  # noqa: A002
        row = self._session.get(orm.EmailTokenOrm, id.value)
        if row is not None:
            self._session.delete(row)


unit_of_work.register_repo(aggregate.User, DefaultUserRepository)
unit_of_work.register_repo(aggregate.EmailToken, DefaultEmailTokenRepository)
