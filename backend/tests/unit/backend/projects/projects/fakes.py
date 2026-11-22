from backend.commons.domain import repositories
from backend.projects.projects.domain.model import aggregate, exceptions, value_objects
from tests.unit import fakes


class FakeProjectRepository(repositories.Repository[aggregate.Project]):
    def __init__(self, outbox: fakes.FakeOutbox) -> None:
        self._outbox = outbox
        self.by_id: dict[value_objects.ProjectId, aggregate.Project] = {}
        self.versions: dict[value_objects.ProjectVersionId, aggregate.ProjectVersion] = {}

    def get(self, id: value_objects.ProjectId) -> aggregate.Project:  # noqa: A002
        try:
            return self.by_id[id].model_copy(deep=True)
        except KeyError:
            raise exceptions.ProjectNotFoundError() from None

    def list_for_owner(
        self, owner_id: value_objects.OwnerId, *, module: value_objects.Module | None
    ) -> list[aggregate.Project]:
        return [
            p.model_copy(deep=True)
            for p in self.by_id.values()
            if p.owner_id == owner_id
            and p.deleted_at is None
            and (module is None or p.module is module)
        ]

    def get_version(
        self, project_id: value_objects.ProjectId, version_id: value_objects.ProjectVersionId
    ) -> aggregate.ProjectVersion:
        version = self.versions.get(version_id)
        if version is None or version.project_id != project_id:
            raise exceptions.ProjectVersionNotFoundError()
        return version.model_copy(deep=True)

    def get_version_by_id(
        self, version_id: value_objects.ProjectVersionId
    ) -> aggregate.ProjectVersion:
        version = self.versions.get(version_id)
        if version is None:
            raise exceptions.ProjectVersionNotFoundError()
        return version.model_copy(deep=True)

    def list_versions(self, project_id: value_objects.ProjectId) -> list[aggregate.VersionSummary]:
        return sorted(
            (v.summary() for v in self.versions.values() if v.project_id == project_id),
            key=lambda s: -s.n,
        )

    def add(self, project: aggregate.Project) -> None:
        self.update(project)

    def update(self, project: aggregate.Project) -> None:
        for version in project.pull_pending_versions():
            self.versions[version.id] = version
        fakes.drain_events(project, self._outbox)
        self.by_id[project.id] = project.model_copy(deep=True)

    def delete(self, id: value_objects.ProjectId) -> None:  # noqa: A002
        self.by_id.pop(id, None)
