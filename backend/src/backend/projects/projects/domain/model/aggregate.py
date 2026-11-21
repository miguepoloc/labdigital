"""`Project` con versiones (contrato §4 "Proyectos", plan §Modelo de datos).

El agregado guarda sólo el *resumen* de la versión actual (`head`) — el contenido (hasta
2 MB) vive en cada `ProjectVersion` y se carga sólo cuando hace falta. Los cambios de
versiones que produce un comando quedan en `_pending_versions` y el repositorio los escribe
en la misma transacción que el proyecto.

Autoguardado: sobrescribe la versión autosave abierta (la actual) mientras tenga menos de
10 min desde que se creó; si es más vieja, o la actual es manual, crea una versión nueva.
`base_version` es el `n` de la versión sobre la que el cliente editó: si ya no es la actual
⇒ 409 `version_conflict`.

`revision` (contrato §6.1) sube en CADA guardado de contenido (autosave, versión manual,
restaurar), también cuando el autosave sobrescribe la versión abierta: así dos pestañas que
editan la misma versión abierta se detectan con `base_revision`.

Versiones entregadas (`locked`): `freeze` marca una versión como inmutable para que una
entrega la referencie. El autoguardado NUNCA sobrescribe una versión bloqueada (crea una
nueva aunque esté dentro de la ventana de 10 min); el repositorio sólo actualiza filas con
`locked = false` y un trigger de Postgres rechaza cualquier cambio de `content` en una fila
bloqueada (defensa en profundidad frente a carreras con una entrega simultánea).
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
    locked: bool = False
    created_at: base_value_objects.PosixTime
    updated_at: base_value_objects.PosixTime


class ProjectVersion(entities.Entity[value_objects.ProjectVersionId]):
    project_id: value_objects.ProjectId
    n: int
    kind: value_objects.VersionKind
    label: str | None
    content: value_objects.ProjectContent
    locked: bool = False

    def summary(self) -> VersionSummary:
        return VersionSummary(
            id=self.id,
            n=self.n,
            kind=self.kind,
            label=self.label,
            size=self.content.size,
            locked=self.locked,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class Project(aggregates.AggregateRoot[value_objects.ProjectId]):
    owner_id: value_objects.OwnerId
    module: value_objects.Module
    name: value_objects.ProjectName
    head: VersionSummary
    last_n: int
    revision: int = 1
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
        self,
        *,
        content: value_objects.ProjectContent,
        base_version: int,
        base_revision: int | None = None,
    ) -> VersionSummary:
        """`base_revision` es opcional por compatibilidad con clientes previos a §6.1; si
        llega y no es la actual ⇒ 409 `version_conflict`."""
        self._ensure_not_deleted()
        if base_version != self.head.n or (
            base_revision is not None and base_revision != self.revision
        ):
            raise self.conflict()
        now = base_value_objects.PosixTime.now()
        window_end = base_value_objects.PosixTime.from_datetime(
            self.head.created_at.to_datetime() + value_objects.AUTOSAVE_WINDOW
        )
        if (
            self.head.kind is value_objects.VersionKind.AUTOSAVE
            and not self.head.locked
            and now < window_end
        ):
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
        if self.head.kind is value_objects.VersionKind.AUTOSAVE and not self.head.locked:
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

    def freeze(self, *, version: ProjectVersion) -> VersionSummary:
        """Bloquea `version` para una entrega (idempotente). Si es la actual y es autosave, se
        promueve además a manual. No sube `revision` (el contenido no cambia): el cliente que
        sigue editando no recibe un 409; su siguiente autoguardado crea una versión nueva."""
        self._ensure_not_deleted()
        if version.project_id != self.id:
            raise exceptions.ProjectVersionNotFoundError()
        if version.locked:
            return version.summary()
        now = base_value_objects.PosixTime.now()
        update: dict[str, object] = {"locked": True, "updated_at": now}
        if version.kind is value_objects.VersionKind.AUTOSAVE:
            update |= {
                "kind": value_objects.VersionKind.MANUAL,
                "label": version.label or "Entregada",
            }
        frozen = version.model_copy(update=update)
        self._pending_versions.append(frozen)
        if frozen.id == self.head.id:
            self.head = frozen.summary()
        return frozen.summary()

    def conflict(self) -> exceptions.VersionConflictError:
        return exceptions.VersionConflictError(
            current_n=self.head.n,
            current_version_id=str(self.head.id),
            current_revision=self.revision,
        )

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
        self.revision += 1
        self.updated_at = now
