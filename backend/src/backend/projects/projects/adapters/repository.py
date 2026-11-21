import sqlalchemy as sa
from sqlalchemy import orm as sa_orm
import sqlalchemy.orm.exc

from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.projects.projects.adapters import orm
from backend.projects.projects.domain.model import aggregate, exceptions, value_objects


def _posix(value: int) -> base_value_objects.PosixTime:
    return base_value_objects.PosixTime(microseconds=value)


def _summary(row: orm.ProjectVersionOrm) -> aggregate.VersionSummary:
    return aggregate.VersionSummary(
        id=value_objects.ProjectVersionId(value=row.id),
        n=row.n,
        kind=value_objects.VersionKind(row.kind),
        label=row.label,
        size=row.size,
        created_at=_posix(row.created_at),
        updated_at=_posix(row.updated_at),
    )


def _to_entity(row: orm.ProjectOrm, head: orm.ProjectVersionOrm) -> aggregate.Project:
    return aggregate.Project(
        id=value_objects.ProjectId(value=row.id),
        owner_id=value_objects.OwnerId(value=row.owner_id),
        module=value_objects.Module(row.module),
        name=value_objects.ProjectName(value=row.name),
        head=_summary(head),
        last_n=row.last_n,
        deleted_at=None if row.deleted_at is None else _posix(row.deleted_at),
        created_at=_posix(row.created_at),
        updated_at=_posix(row.updated_at),
        version=row.version,
    )


def _to_orm(project: aggregate.Project) -> orm.ProjectOrm:
    return orm.ProjectOrm(
        id=project.id.value,
        owner_id=project.owner_id.value,
        module=project.module.value,
        name=project.name.value,
        current_version_id=project.head.id.value,
        last_n=project.last_n,
        deleted_at=None if project.deleted_at is None else project.deleted_at.microseconds,
        created_at=project.created_at.microseconds,
        updated_at=project.updated_at.microseconds,
        version=project.version,
    )


def _version_to_orm(version: aggregate.ProjectVersion) -> orm.ProjectVersionOrm:
    return orm.ProjectVersionOrm(
        id=version.id.value,
        project_id=version.project_id.value,
        n=version.n,
        kind=version.kind.value,
        label=version.label,
        content=version.content.data,
        size=version.content.size,
        created_at=version.created_at.microseconds,
        updated_at=version.updated_at.microseconds,
    )


def _version_to_entity(row: orm.ProjectVersionOrm) -> aggregate.ProjectVersion:
    return aggregate.ProjectVersion(
        id=value_objects.ProjectVersionId(value=row.id),
        project_id=value_objects.ProjectId(value=row.project_id),
        n=row.n,
        kind=value_objects.VersionKind(row.kind),
        label=row.label,
        content=value_objects.ProjectContent(data=dict(row.content), size=row.size),
        created_at=_posix(row.created_at),
        updated_at=_posix(row.updated_at),
    )


class DefaultProjectRepository(repositories.Repository[aggregate.Project]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: value_objects.ProjectId) -> aggregate.Project:  # noqa: A002
        row = self._session.get(orm.ProjectOrm, id.value)
        if row is None:
            raise exceptions.ProjectNotFoundError()
        head = self._session.get(orm.ProjectVersionOrm, row.current_version_id)
        if head is None:
            raise exceptions.ProjectNotFoundError()
        return _to_entity(row, head)

    def list_for_owner(
        self, owner_id: value_objects.OwnerId, *, module: value_objects.Module | None
    ) -> list[aggregate.Project]:
        stmt = (
            sa.select(orm.ProjectOrm, orm.ProjectVersionOrm)
            .join(
                orm.ProjectVersionOrm, orm.ProjectVersionOrm.id == orm.ProjectOrm.current_version_id
            )
            .where(orm.ProjectOrm.owner_id == owner_id.value, orm.ProjectOrm.deleted_at.is_(None))
            .order_by(orm.ProjectOrm.updated_at.desc())
        )
        if module is not None:
            stmt = stmt.where(orm.ProjectOrm.module == module.value)
        return [_to_entity(project, head) for project, head in self._session.execute(stmt).tuples()]

    def get_version(
        self, project_id: value_objects.ProjectId, version_id: value_objects.ProjectVersionId
    ) -> aggregate.ProjectVersion:
        row = self._session.get(orm.ProjectVersionOrm, version_id.value)
        if row is None or row.project_id != project_id.value:
            raise exceptions.ProjectVersionNotFoundError()
        return _version_to_entity(row)

    def list_versions(self, project_id: value_objects.ProjectId) -> list[aggregate.VersionSummary]:
        stmt = (
            sa.select(orm.ProjectVersionOrm)
            .where(orm.ProjectVersionOrm.project_id == project_id.value)
            .order_by(orm.ProjectVersionOrm.n.desc())
        )
        return [_summary(row) for row in self._session.scalars(stmt)]

    def add(self, project: aggregate.Project) -> None:
        self._session.add(_to_orm(project))
        self._session.flush()
        self._write_versions(project)
        repository_helpers.publish_events(self._session, project)

    def update(self, project: aggregate.Project) -> None:
        self._write_versions(project)
        self._session.merge(_to_orm(project))
        try:
            self._session.flush()
        except sqlalchemy.orm.exc.StaleDataError as exc:
            raise commons_exceptions.ConcurrentModificationError(
                "El proyecto cambió a la vez desde otra pestaña. Recarga para continuar.",
                code="version_conflict",
            ) from exc
        repository_helpers.publish_events(self._session, project)

    def delete(self, id: value_objects.ProjectId) -> None:  # noqa: A002
        row = self._session.get(orm.ProjectOrm, id.value)
        if row is not None:
            self._session.delete(row)

    def _write_versions(self, project: aggregate.Project) -> None:
        for version in project.pull_pending_versions():
            self._session.merge(_version_to_orm(version))
        self._session.flush()


unit_of_work.register_repo(aggregate.Project, DefaultProjectRepository)
