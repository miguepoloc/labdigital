from typing import Any, Self

from backend.commons.application import dto
from backend.commons.domain import value_objects as base_value_objects
from backend.projects.projects.domain.model import aggregate


def _iso(value: base_value_objects.PosixTime) -> str:
    return value.to_datetime().isoformat().replace("+00:00", "Z")


class CreateProjectInputDTO(dto.BaseDTO):
    name: str
    module: str
    content: dict[str, Any]


class AutosaveInputDTO(dto.BaseDTO):
    content: dict[str, Any]
    base_version: int
    base_revision: int | None = None


class VersionOutputDTO(dto.BaseDTO):
    id: str
    n: int
    kind: str
    label: str | None
    size: int
    locked: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_summary(cls, summary: aggregate.VersionSummary) -> Self:
        return cls(
            id=str(summary.id),
            n=summary.n,
            kind=summary.kind.value,
            label=summary.label,
            size=summary.size,
            locked=summary.locked,
            created_at=_iso(summary.created_at),
            updated_at=_iso(summary.updated_at),
        )


class VersionDetailOutputDTO(VersionOutputDTO):
    content: dict[str, Any]

    @classmethod
    def from_version(cls, version: aggregate.ProjectVersion) -> Self:
        base = VersionOutputDTO.from_summary(version.summary())
        return cls(**base.model_dump(), content=version.content.data)


class ProjectOutputDTO(dto.BaseDTO):
    """`Project` (listado): sin `content`."""

    id: str
    name: str
    module: str
    revision: int
    current_version: VersionOutputDTO
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, project: aggregate.Project) -> Self:
        return cls(
            id=str(project.id),
            name=project.name.value,
            module=project.module.value,
            revision=project.revision,
            current_version=VersionOutputDTO.from_summary(project.head),
            created_at=_iso(project.created_at),
            updated_at=_iso(project.updated_at),
        )


class ProjectDetailOutputDTO(ProjectOutputDTO):
    """`GET /projects/{id}`: incluye `content` de la versión actual (contrato §4)."""

    content: dict[str, Any]

    @classmethod
    def from_entity_and_content(cls, project: aggregate.Project, content: dict[str, Any]) -> Self:
        base = ProjectOutputDTO.from_entity(project)
        return cls(**base.model_dump(), content=content)


class AutosaveOutputDTO(dto.BaseDTO):
    version_id: str
    n: int
    revision: int


class FrozenVersionOutputDTO(dto.BaseDTO):
    """Versión bloqueada para una entrega (la referencia que guarda `submissions`)."""

    project_id: str
    project_name: str
    version_id: str
    n: int
    size: int


class FrozenContentOutputDTO(FrozenVersionOutputDTO):
    content: dict[str, Any]
