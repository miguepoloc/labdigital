"""`Project` con versiones (contrato §4 "Proyectos", plan §Modelo de datos).

El agregado guarda sólo el *resumen* de la versión actual (`head`) — el contenido (hasta
2 MB) vive en cada `ProjectVersion` y se carga sólo cuando hace falta. Los cambios de
versiones que produce un comando quedan en `_pending_versions` y el repositorio los escribe
en la misma transacción que el proyecto.

Autoguardado: sobrescribe la versión autosave abierta (la actual) mientras tenga menos de
10 min desde que se creó; si es más vieja, o la actual es manual, crea una versión nueva.
`base_version` es el `n` de la versión sobre la que el cliente editó: si ya no es la actual
⇒ 409 `version_conflict`.
"""

from typing import Self

import pydantic

from backend.commons.domain import aggregates, entities
from backend.commons.domain import value_objects as base_value_objects
from backend.projects.projects.domain.model import events, exceptions, value_objects


class VersionSummary(base_value_objects.ValueObject):
    id: value_objects.ProjectVersionId
    n: int
    kind: value_objects.VersionKind
    label: str | None
    size: int
    created_at: base_value_objects.PosixTime
    updated_at: base_value_objects.PosixTime


class ProjectVersion(entities.Entity[value_objects.ProjectVersionId]):
    project_id: value_objects.ProjectId
    n: int
    kind: value_objects.VersionKind
    label: str | None
    content: value_objects.ProjectContent

    def summary(self) -> VersionSummary:
        return VersionSummary(
            id=self.id,
            n=self.n,
            kind=self.kind,
            label=self.label,
            size=self.content.size,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class Project(aggregates.AggregateRoot[value_objects.ProjectId]):
    owner_id: value_objects.OwnerId
    module: value_objects.Module
    name: value_objects.ProjectName
    head: VersionSummary
    last_n: int
    deleted_at: base_value_objects.PosixTime | None = None
    _pending_versions: list[ProjectVersion] = pydantic.PrivateAttr(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        owner_id: value_objects.OwnerId,
        module: value_objects.Module,
        name: value_objects.ProjectName,
        content: value_objects.ProjectContent,
    ) -> Self:
        now = base_value_objects.PosixTime.now()
        project_id = value_objects.ProjectId.new()
        first = ProjectVersion(
            id=value_objects.ProjectVersionId.new(),
            project_id=project_id,
            n=1,
            kind=value_objects.VersionKind.AUTOSAVE,
            label=None,
            content=content,
            created_at=now,
            updated_at=now,
        )
        project = cls(
            id=project_id,
            owner_id=owner_id,
            module=module,
            name=name,
            head=first.summary(),
            last_n=1,
            created_at=now,
            updated_at=now,
        )
        project._pending_versions.append(first)
        project.record_event(events.ProjectCreated(project_id=project_id, owner_id=owner_id))
        return project

    def ensure_accessible_by(self, owner_id: value_objects.OwnerId) -> None:
        """Sólo el dueño (las entregas lo ampliarán). Ajeno o borrado ⇒ 404."""
        if self.deleted_at is not None or self.owner_id != owner_id:
            raise exceptions.ProjectNotFoundError()

    def autosave(
        self, *, content: value_objects.ProjectContent, base_version: int
    ) -> VersionSummary:
        self._ensure_not_deleted()
        if base_version != self.head.n:
            raise exceptions.VersionConflictError(
                current_n=self.head.n, current_version_id=str(self.head.id)
            )
        now = base_value_objects.PosixTime.now()
        window_end = base_value_objects.PosixTime.from_datetime(
            self.head.created_at.to_datetime() + value_objects.AUTOSAVE_WINDOW
        )
        if self.head.kind is value_objects.VersionKind.AUTOSAVE and now < window_end:
            version = ProjectVersion(
                id=self.head.id,
                project_id=self.id,
                n=self.head.n,
                kind=value_objects.VersionKind.AUTOSAVE,
                label=None,
                content=content,
                created_at=self.head.created_at,
                updated_at=now,
            )
        else:
            version = self._new_version(
                content=content, kind=value_objects.VersionKind.AUTOSAVE, label=None, now=now
            )
        self._set_head(version, now)
        return self.head

    def save_manual(
        self, *, label: value_objects.VersionLabel | None, head_version: ProjectVersion
    ) -> VersionSummary:
        """ "Guardar versión": si la actual es autosave, se congela como manual (mismo `n`,
        sin duplicar contenido); si ya es manual, se crea una copia manual nueva."""
        self._ensure_not_deleted()
        if head_version.id != self.head.id:
            raise exceptions.ProjectVersionNotFoundError()
        now = base_value_objects.PosixTime.now()
        label_value = label.value if label and label.value else None
        if self.head.kind is value_objects.VersionKind.AUTOSAVE:
            version = head_version.model_copy(
                update={
                    "kind": value_objects.VersionKind.MANUAL,
                    "label": label_value,
                    "updated_at": now,
                }
            )
        else:
            version = self._new_version(
                content=head_version.content,
                kind=value_objects.VersionKind.MANUAL,
                label=label_value,
                now=now,
            )
        self._set_head(version, now)
        return self.head

    def restore(self, *, version: ProjectVersion) -> VersionSummary:
        """Crea una versión manual nueva con el contenido de `version` (no reescribe la
        historia)."""
        self._ensure_not_deleted()
        if version.project_id != self.id:
            raise exceptions.ProjectVersionNotFoundError()
        now = base_value_objects.PosixTime.now()
        restored = self._new_version(
            content=version.content,
            kind=value_objects.VersionKind.MANUAL,
            label=f"Restaurada desde la versión {version.n}",
            now=now,
        )
        self._set_head(restored, now)
        return self.head

    def rename(self, name: value_objects.ProjectName) -> None:
        self._ensure_not_deleted()
        if name != self.name:
            self.name = name
            self.touch()

    def soft_delete(self) -> None:
        if self.deleted_at is None:
            self.deleted_at = base_value_objects.PosixTime.now()
            self.touch()
            self.record_event(events.ProjectDeleted(project_id=self.id))

    def pull_pending_versions(self) -> list[ProjectVersion]:
        pending, self._pending_versions = self._pending_versions, []
        return pending

    def _ensure_not_deleted(self) -> None:
        if self.deleted_at is not None:
            raise exceptions.ProjectNotFoundError()

    def _new_version(
        self,
        *,
        content: value_objects.ProjectContent,
        kind: value_objects.VersionKind,
        label: str | None,
        now: base_value_objects.PosixTime,
    ) -> ProjectVersion:
        self.last_n += 1
        return ProjectVersion(
            id=value_objects.ProjectVersionId.new(),
            project_id=self.id,
            n=self.last_n,
            kind=kind,
            label=label,
            content=content,
            created_at=now,
            updated_at=now,
        )

    def _set_head(self, version: ProjectVersion, now: base_value_objects.PosixTime) -> None:
        self._pending_versions.append(version)
        self.head = version.summary()
        self.updated_at = now
