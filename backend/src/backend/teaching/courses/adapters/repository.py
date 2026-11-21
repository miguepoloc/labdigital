import sqlalchemy as sa
from sqlalchemy import orm as sa_orm
import sqlalchemy.exc
import sqlalchemy.orm.exc

from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.adapters import orm
from backend.teaching.courses.domain.model import aggregate, exceptions, value_objects

_MAX_CODE_RETRIES = 5


def _posix(value: int) -> base_value_objects.PosixTime:
    return base_value_objects.PosixTime(microseconds=value)


def _course_to_orm(course: aggregate.Course) -> orm.CourseOrm:
    return orm.CourseOrm(
        id=course.id.value,
        owner_id=course.owner_id.value,
        name=course.name.value,
        period=course.period.value,
        description=course.description.value,
        join_code=course.join_code.value,
        archived_at=None if course.archived_at is None else course.archived_at.microseconds,
        created_at=course.created_at.microseconds,
        updated_at=course.updated_at.microseconds,
        version=course.version,
    )


def _course_to_entity(row: orm.CourseOrm) -> aggregate.Course:
    return aggregate.Course(
        id=teaching_value_objects.CourseId(value=row.id),
        owner_id=teaching_value_objects.UserRef(value=row.owner_id),
        name=value_objects.CourseName(value=row.name),
        period=value_objects.Period(value=row.period),
        description=value_objects.Description(value=row.description),
        join_code=value_objects.JoinCode(value=row.join_code),
        archived_at=None if row.archived_at is None else _posix(row.archived_at),
        created_at=_posix(row.created_at),
        updated_at=_posix(row.updated_at),
        version=row.version,
    )


def _membership_to_orm(membership: aggregate.Membership) -> orm.MembershipOrm:
    return orm.MembershipOrm(
        id=membership.id.value,
        course_id=membership.course_id.value,
        user_id=membership.user_id.value,
        role=membership.role.value,
        status=membership.status.value,
        created_at=membership.created_at.microseconds,
        updated_at=membership.updated_at.microseconds,
        version=membership.version,
    )


def _membership_to_entity(row: orm.MembershipOrm) -> aggregate.Membership:
    return aggregate.Membership(
        id=value_objects.MembershipId(value=row.id),
        course_id=teaching_value_objects.CourseId(value=row.course_id),
        user_id=teaching_value_objects.UserRef(value=row.user_id),
        role=value_objects.MembershipRole(row.role),
        status=value_objects.MembershipStatus(row.status),
        created_at=_posix(row.created_at),
        updated_at=_posix(row.updated_at),
        version=row.version,
    )


def _is_join_code_collision(exc: sqlalchemy.exc.IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    return constraint == "courses_join_code_key"


def _stale(exc: Exception) -> commons_exceptions.ConcurrentModificationError:
    return commons_exceptions.ConcurrentModificationError(
        "El curso cambió a la vez en otra petición; inténtalo de nuevo.",
        code="concurrent_modification",
    )


class DefaultCourseRepository(repositories.Repository[aggregate.Course]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: teaching_value_objects.CourseId) -> aggregate.Course:  # noqa: A002
        row = self._session.get(orm.CourseOrm, id.value)
        if row is None:
            raise exceptions.CourseNotFoundError()
        return _course_to_entity(row)

    def get_by_join_code(self, code: value_objects.JoinCode) -> aggregate.Course:
        row = self._session.execute(
            sa.select(orm.CourseOrm).where(orm.CourseOrm.join_code == code.value)
        ).scalar_one_or_none()
        if row is None:
            raise exceptions.InvalidJoinCodeError()
        return _course_to_entity(row)

    def list_by_ids(self, ids: list[teaching_value_objects.CourseId]) -> list[aggregate.Course]:
        if not ids:
            return []
        stmt = (
            sa.select(orm.CourseOrm)
            .where(orm.CourseOrm.id.in_([i.value for i in ids]))
            .order_by(orm.CourseOrm.created_at.desc())
        )
        return [_course_to_entity(row) for row in self._session.scalars(stmt)]

    def add(self, course: aggregate.Course) -> None:
        """El código de unión es único; ante una colisión (improbable: 31^8) se genera otro
        dentro de un SAVEPOINT sin romper la transacción exterior."""
        for attempt in range(_MAX_CODE_RETRIES):
            try:
                with self._session.begin_nested():
                    self._session.add(_course_to_orm(course))
                    self._session.flush()
                break
            except sqlalchemy.exc.IntegrityError as exc:
                if not _is_join_code_collision(exc) or attempt == _MAX_CODE_RETRIES - 1:
                    raise
                course.join_code = value_objects.JoinCode.new()
        repository_helpers.publish_events(self._session, course)

    def update(self, course: aggregate.Course) -> None:
        for attempt in range(_MAX_CODE_RETRIES):
            try:
                with self._session.begin_nested():
                    self._session.merge(_course_to_orm(course))
                    self._session.flush()
                break
            except sqlalchemy.orm.exc.StaleDataError as exc:
                raise _stale(exc) from exc
            except sqlalchemy.exc.IntegrityError as exc:
                if not _is_join_code_collision(exc) or attempt == _MAX_CODE_RETRIES - 1:
                    raise
                course.join_code = value_objects.JoinCode.new()
        repository_helpers.publish_events(self._session, course)

    def delete(self, id: teaching_value_objects.CourseId) -> None:  # noqa: A002
        row = self._session.get(orm.CourseOrm, id.value)
        if row is not None:
            self._session.delete(row)


class DefaultMembershipRepository(repositories.Repository[aggregate.Membership]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: value_objects.MembershipId) -> aggregate.Membership:  # noqa: A002
        row = self._session.get(orm.MembershipOrm, id.value)
        if row is None:
            raise exceptions.MembershipNotFoundError()
        return _membership_to_entity(row)

    def find(
        self, course_id: teaching_value_objects.CourseId, user_id: teaching_value_objects.UserRef
    ) -> aggregate.Membership | None:
        row = self._session.execute(
            sa.select(orm.MembershipOrm).where(
                orm.MembershipOrm.course_id == course_id.value,
                orm.MembershipOrm.user_id == user_id.value,
            )
        ).scalar_one_or_none()
        return None if row is None else _membership_to_entity(row)

    def list_for_course(
        self,
        course_id: teaching_value_objects.CourseId,
        *,
        status: value_objects.MembershipStatus | None = None,
        role: value_objects.MembershipRole | None = None,
    ) -> list[aggregate.Membership]:
        stmt = (
            sa.select(orm.MembershipOrm)
            .where(orm.MembershipOrm.course_id == course_id.value)
            .order_by(orm.MembershipOrm.created_at)
        )
        if status is not None:
            stmt = stmt.where(orm.MembershipOrm.status == status.value)
        if role is not None:
            stmt = stmt.where(orm.MembershipOrm.role == role.value)
        return [_membership_to_entity(row) for row in self._session.scalars(stmt)]

    def count(
        self, course_id: teaching_value_objects.CourseId, status: value_objects.MembershipStatus
    ) -> int:
        """Estudiantes del curso en `status` (el docente no cuenta)."""
        return int(
            self._session.execute(
                sa.select(sa.func.count())
                .select_from(orm.MembershipOrm)
                .where(
                    orm.MembershipOrm.course_id == course_id.value,
                    orm.MembershipOrm.status == status.value,
                    orm.MembershipOrm.role == value_objects.MembershipRole.ESTUDIANTE.value,
                )
            ).scalar_one()
        )

    def list_for_user(self, user_id: teaching_value_objects.UserRef) -> list[aggregate.Membership]:
        stmt = sa.select(orm.MembershipOrm).where(orm.MembershipOrm.user_id == user_id.value)
        return [_membership_to_entity(row) for row in self._session.scalars(stmt)]

    def add(self, membership: aggregate.Membership) -> None:
        """Dos solicitudes simultáneas del mismo usuario chocan en la unicidad
        `(course_id, user_id)`: la segunda ve un `ConflictError` reintentable."""
        try:
            with self._session.begin_nested():
                self._session.add(_membership_to_orm(membership))
                self._session.flush()
        except sqlalchemy.exc.IntegrityError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                "Ya hay una solicitud en curso para este curso.", code="concurrent_modification"
            ) from exc
        repository_helpers.publish_events(self._session, membership)

    def update(self, membership: aggregate.Membership) -> None:
        self._session.merge(_membership_to_orm(membership))
        try:
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise _stale(exc) from exc
        repository_helpers.publish_events(self._session, membership)

    def delete(self, id: value_objects.MembershipId) -> None:  # noqa: A002
        row = self._session.get(orm.MembershipOrm, id.value)
        if row is not None:
            self._session.delete(row)


unit_of_work.register_repo(aggregate.Course, DefaultCourseRepository)
unit_of_work.register_repo(aggregate.Membership, DefaultMembershipRepository)
