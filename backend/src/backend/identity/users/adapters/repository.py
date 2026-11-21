import sqlalchemy as sa
from sqlalchemy.orm import Session
import sqlalchemy.orm.exc

from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.users.adapters import orm
from backend.identity.users.domain.model import aggregate, exceptions, value_objects


def _to_orm(user: aggregate.User) -> orm.UserOrm:
    return orm.UserOrm(
        id=user.id.value,
        email=user.email.value,
        full_name=user.full_name,
        password_salt_hex=user.hashed_password.salt_hex,
        password_hash_hex=user.hashed_password.hash_hex,
        is_active=user.is_active,
        created_at=user.created_at.microseconds,
        updated_at=user.updated_at.microseconds,
        version=user.version,
    )


def _to_entity(user_orm: orm.UserOrm) -> aggregate.User:
    return aggregate.User(
        id=value_objects.UserId(value=user_orm.id),
        email=value_objects.Email(value=user_orm.email),
        full_name=user_orm.full_name,
        hashed_password=value_objects.HashedPassword(
            salt_hex=user_orm.password_salt_hex, hash_hex=user_orm.password_hash_hex
        ),
        is_active=user_orm.is_active,
        created_at=base_value_objects.PosixTime(microseconds=user_orm.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=user_orm.updated_at),
        version=user_orm.version,
    )


class DefaultUserRepository(repositories.Repository[aggregate.User]):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, id: value_objects.UserId) -> aggregate.User:  # noqa: A002
        user_orm = self._session.get(orm.UserOrm, id.value)
        if user_orm is None:
            raise exceptions.UserNotFoundError(identifier=id)
        return _to_entity(user_orm)

    def get_by_email(self, email: value_objects.Email) -> aggregate.User:
        stmt = sa.select(orm.UserOrm).where(orm.UserOrm.email == email.value)
        user_orm = self._session.execute(stmt).scalar_one_or_none()
        if user_orm is None:
            raise exceptions.UserNotFoundError(identifier=email)
        return _to_entity(user_orm)

    def add(self, user: aggregate.User) -> None:
        # HumanFriendlyId-keyed (ARCHITECTURE.md §5.2), so this goes through
        # insert_with_id_retry the same way commerce.orders.Order's add() does (§7.1).
        row = _to_orm(user)
        final_id = repository_helpers.insert_with_id_retry(self._session, row)
        if final_id != user.id.value:
            user.id = value_objects.UserId(value=final_id)
        repository_helpers.publish_events(self._session, user)

    def update(self, user: aggregate.User) -> None:
        self._session.merge(_to_orm(user))
        try:
            self._session.flush()  # forces the version_id_col check now, not at commit time
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                f"User [{user.id}] changed concurrently — reload and retry.",
                code="CONCURRENT_MODIFICATION",
            ) from exc
        repository_helpers.publish_events(self._session, user)

    def delete(self, id: value_objects.UserId) -> None:  # noqa: A002
        user_orm = self._session.get(orm.UserOrm, id.value)
        if user_orm is not None:
            self._session.delete(user_orm)


unit_of_work.register_repo(aggregate.User, DefaultUserRepository)
