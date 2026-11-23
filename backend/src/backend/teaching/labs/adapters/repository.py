import sqlalchemy as sa
from sqlalchemy import orm as sa_orm
import sqlalchemy.exc
import sqlalchemy.orm.exc

from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.labs.adapters import orm
from backend.teaching.labs.domain.model import aggregate, exceptions, value_objects

_MAX_CODE_RETRIES = 5


def _posix(value: int | None) -> base_value_objects.PosixTime | None:
    return None if value is None else base_value_objects.PosixTime(microseconds=value)


def _micros(value: base_value_objects.PosixTime | None) -> int | None:
    return None if value is None else value.microseconds


def _lab_to_orm(lab: aggregate.Lab) -> orm.LabOrm:
    return orm.LabOrm(
        id=lab.id.value,
        course_id=lab.course_id.value,
        created_by=lab.created_by.value,
        title=lab.title.value,
        statement_md=lab.statement_md.value,
        module=lab.module.value,
        opens_at=_micros(lab.schedule.opens_at),
        due_at=_micros(lab.schedule.due_at),
        deadline_policy=lab.schedule.deadline_policy.value,
        team_mode=lab.team_setup.team_mode.value,
        max_team_size=lab.team_setup.max_team_size,
        grade_scale=lab.grade_scale.to_storage(),
        allow_resubmission=lab.allow_resubmission,
        published_at=_micros(lab.published_at),
        created_at=lab.created_at.microseconds,
        updated_at=lab.updated_at.microseconds,
        version=lab.version,
    )


def _lab_to_entity(row: orm.LabOrm) -> aggregate.Lab:
    return aggregate.Lab(
        id=teaching_value_objects.LabId(value=row.id),
        course_id=teaching_value_objects.CourseId(value=row.course_id),
        created_by=teaching_value_objects.UserRef(value=row.created_by),
        title=value_objects.LabTitle(value=row.title),
        statement_md=value_objects.StatementMd(value=row.statement_md),
        module=value_objects.LabModule(row.module),
        schedule=value_objects.Schedule(
            opens_at=_posix(row.opens_at),
            due_at=_posix(row.due_at),
            deadline_policy=value_objects.DeadlinePolicy(row.deadline_policy),
        ),
        team_setup=value_objects.TeamSetup(
            team_mode=value_objects.TeamMode(row.team_mode), max_team_size=row.max_team_size
        ),
        grade_scale=teaching_value_objects.GradeScale.from_storage(dict(row.grade_scale)),
        allow_resubmission=row.allow_resubmission,
        published_at=_posix(row.published_at),
        created_at=base_value_objects.PosixTime(microseconds=row.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=row.updated_at),
        version=row.version,
    )


def _stale() -> commons_exceptions.ConcurrentModificationError:
    return commons_exceptions.ConcurrentModificationError(
        "Cambió a la vez en otra petición; recarga e inténtalo de nuevo.",
        code="concurrent_modification",
    )


class DefaultLabRepository(repositories.Repository[aggregate.Lab]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: teaching_value_objects.LabId) -> aggregate.Lab:  # noqa: A002
        row = self._session.get(orm.LabOrm, id.value)
        if row is None:
            raise exceptions.LabNotFoundError()
        return _lab_to_entity(row)

    def list_for_course(
        self, course_id: teaching_value_objects.CourseId, *, published_only: bool
    ) -> list[aggregate.Lab]:
        stmt = (
            sa.select(orm.LabOrm)
            .where(orm.LabOrm.course_id == course_id.value)
            .order_by(orm.LabOrm.created_at)
        )
        if published_only:
            stmt = stmt.where(orm.LabOrm.published_at.is_not(None))
        return [_lab_to_entity(row) for row in self._session.scalars(stmt)]

    def add(self, lab: aggregate.Lab) -> None:
        self._session.add(_lab_to_orm(lab))
        self._session.flush()
        repository_helpers.publish_events(self._session, lab)

    def update(self, lab: aggregate.Lab) -> None:
        try:
            self._session.merge(_lab_to_orm(lab))
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise _stale() from exc
        repository_helpers.publish_events(self._session, lab)

    def delete(self, id: teaching_value_objects.LabId) -> None:  # noqa: A002
        row = self._session.get(orm.LabOrm, id.value)
        if row is not None:
            self._session.delete(row)


def _team_to_orm(team: aggregate.Team) -> orm.TeamOrm:
    return orm.TeamOrm(
        id=team.id.value,
        lab_id=team.lab_id.value,
        course_id=team.course_id.value,
        name=team.name.value,
        join_code=team.join_code.value,
        locked=team.locked,
        created_at=team.created_at.microseconds,
        updated_at=team.updated_at.microseconds,
        version=team.version,
    )


class DefaultTeamRepository(repositories.Repository[aggregate.Team]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: teaching_value_objects.TeamId) -> aggregate.Team:  # noqa: A002
        row = self._session.get(orm.TeamOrm, id.value)
        if row is None:
            raise exceptions.TeamNotFoundError()
        return self._to_entity(row)

    def get_by_code(
        self, lab_id: teaching_value_objects.LabId, code: value_objects.TeamJoinCode
    ) -> aggregate.Team:
        row = self._session.execute(
            sa.select(orm.TeamOrm).where(
                orm.TeamOrm.lab_id == lab_id.value, orm.TeamOrm.join_code == code.value
            )
        ).scalar_one_or_none()
        if row is None:
            raise exceptions.InvalidTeamCodeError()
        return self._to_entity(row)

    def find_for_member(
        self, lab_id: teaching_value_objects.LabId, user_id: teaching_value_objects.UserRef
    ) -> aggregate.Team | None:
        team_id = self._session.execute(
            sa.select(orm.TeamMemberOrm.team_id).where(
                orm.TeamMemberOrm.lab_id == lab_id.value,
                orm.TeamMemberOrm.user_id == user_id.value,
            )
        ).scalar_one_or_none()
        if team_id is None:
            return None
        return self.get(teaching_value_objects.TeamId(value=team_id))

    def list_for_lab(self, lab_id: teaching_value_objects.LabId) -> list[aggregate.Team]:
        stmt = (
            sa.select(orm.TeamOrm)
            .where(orm.TeamOrm.lab_id == lab_id.value)
            .order_by(orm.TeamOrm.created_at)
        )
        return [self._to_entity(row) for row in self._session.scalars(stmt)]

    def add(self, team: aggregate.Team) -> None:
        for attempt in range(_MAX_CODE_RETRIES):
            try:
                with self._session.begin_nested():
                    self._session.add(_team_to_orm(team))
                    self._session.flush()
                break
            except sqlalchemy.exc.IntegrityError as exc:
                if _constraint(exc) != "uq_teams_lab_join_code" or attempt == _MAX_CODE_RETRIES - 1:
                    raise
                team.join_code = value_objects.TeamJoinCode.new()
        self._sync_members(team)
        repository_helpers.publish_events(self._session, team)

    def update(self, team: aggregate.Team) -> None:
        try:
            self._session.merge(_team_to_orm(team))
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise _stale() from exc
        self._sync_members(team)
        repository_helpers.publish_events(self._session, team)

    def delete(self, id: teaching_value_objects.TeamId) -> None:  # noqa: A002
        """Los integrantes caen en cascada. Una entrega del equipo (FK `RESTRICT`, también
        si llega a la vez) ⇒ `TeamHasSubmissionsError`."""
        row = self._session.get(orm.TeamOrm, id.value)
        if row is None:
            return
        try:
            with self._session.begin_nested():
                self._session.execute(
                    sa.delete(orm.TeamMemberOrm).where(orm.TeamMemberOrm.team_id == id.value)
                )
                self._session.delete(row)
                self._session.flush()
        except sqlalchemy.exc.IntegrityError as exc:
            raise exceptions.TeamHasSubmissionsError() from exc

    def _sync_members(self, team: aggregate.Team) -> None:
        """Reescribe los integrantes. La unicidad `(lab_id, user_id)` traduce "ya está en
        otro equipo de este lab" (también en carreras) a `AlreadyInTeamError`."""
        try:
            with self._session.begin_nested():
                self._session.execute(
                    sa.delete(orm.TeamMemberOrm).where(orm.TeamMemberOrm.team_id == team.id.value)
                )
                for position, member in enumerate(team.members):
                    self._session.add(
                        orm.TeamMemberOrm(
                            team_id=team.id.value,
                            user_id=member.value,
                            lab_id=team.lab_id.value,
                            position=position,
                        )
                    )
                self._session.flush()
        except sqlalchemy.exc.IntegrityError as exc:
            if _constraint(exc) == "uq_team_members_lab_user":
                raise exceptions.AlreadyInTeamError() from exc
            raise

    def _to_entity(self, row: orm.TeamOrm) -> aggregate.Team:
        members = self._session.scalars(
            sa.select(orm.TeamMemberOrm.user_id)
            .where(orm.TeamMemberOrm.team_id == row.id)
            .order_by(orm.TeamMemberOrm.position)
        ).all()
        return aggregate.Team(
            id=teaching_value_objects.TeamId(value=row.id),
            lab_id=teaching_value_objects.LabId(value=row.lab_id),
            course_id=teaching_value_objects.CourseId(value=row.course_id),
            name=value_objects.TeamName(value=row.name),
            join_code=value_objects.TeamJoinCode(value=row.join_code),
            locked=row.locked,
            members=[teaching_value_objects.UserRef(value=m) for m in members],
            created_at=base_value_objects.PosixTime(microseconds=row.created_at),
            updated_at=base_value_objects.PosixTime(microseconds=row.updated_at),
            version=row.version,
        )


def _constraint(exc: sqlalchemy.exc.IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


unit_of_work.register_repo(aggregate.Lab, DefaultLabRepository)
unit_of_work.register_repo(aggregate.Team, DefaultTeamRepository)
