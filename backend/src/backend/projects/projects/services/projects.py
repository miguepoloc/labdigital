"""Capa de aplicación de `projects.projects`. Autorización aquí, no en la UI: todo caso de
uso recibe el `owner_id` del access verificado y `Project.ensure_accessible_by` decide."""

import typing
import uuid

from backend.commons.adapters import unit_of_work
from backend.commons.domain import exceptions as commons_exceptions
from backend.projects.projects.adapters import repository
from backend.projects.projects.domain.model import aggregate, exceptions, value_objects
from backend.projects.projects.services import dto


def list_projects(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, module: str | None
) -> list[dto.ProjectOutputDTO]:
    module_vo = _module(module) if module else None
    with uow.transaction():
        projects = _repo(uow).list_for_owner(_owner(owner_id), module=module_vo)
    return [dto.ProjectOutputDTO.from_entity(p) for p in projects]


def create_project(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, input_dto: dto.CreateProjectInputDTO
) -> dto.ProjectDetailOutputDTO:
    module = _module(input_dto.module)
    content = value_objects.ProjectContent.for_module(module, input_dto.content)
    project = aggregate.Project.create(
        owner_id=_owner(owner_id),
        module=module,
        name=value_objects.ProjectName(value=input_dto.name),
        content=content,
    )
    with uow.transaction():
        uow.repo(aggregate.Project).add(project)
    return dto.ProjectDetailOutputDTO.from_entity_and_content(project, content.data)


def get_project(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, project_id: str
) -> dto.ProjectDetailOutputDTO:
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        head = repo.get_version(project.id, project.head.id)
    return dto.ProjectDetailOutputDTO.from_entity_and_content(project, head.content.data)


def rename_project(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, project_id: str, name: str
) -> dto.ProjectOutputDTO:
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        project.rename(value_objects.ProjectName(value=name))
        repo.update(project)
    return dto.ProjectOutputDTO.from_entity(project)


def delete_project(*, uow: unit_of_work.UnitOfWork, owner_id: str, project_id: str) -> None:
    """Borrado lógico (`deleted_at`): las versiones se conservan (las entregas congeladas
    que apunten a ellas siguen siendo válidas)."""
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        project.soft_delete()
        repo.update(project)


def autosave(
    *,
    uow: unit_of_work.UnitOfWork,
    owner_id: str,
    project_id: str,
    input_dto: dto.AutosaveInputDTO,
) -> dto.AutosaveOutputDTO:
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        content = value_objects.ProjectContent.for_module(project.module, input_dto.content)
        head = project.autosave(
            content=content,
            base_version=input_dto.base_version,
            base_revision=input_dto.base_revision,
        )
        repo.update(project)
    return dto.AutosaveOutputDTO(version_id=str(head.id), n=head.n, revision=project.revision)


def create_manual_version(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, project_id: str, label: str | None
) -> dto.ProjectDetailOutputDTO:
    """Devuelve `Project` con la `revision` nueva (contrato §6.1)."""
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        head_version = repo.get_version(project.id, project.head.id)
        project.save_manual(
            label=value_objects.VersionLabel(value=label) if label else None,
            head_version=head_version,
        )
        repo.update(project)
    return dto.ProjectDetailOutputDTO.from_entity_and_content(project, head_version.content.data)


def list_versions(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, project_id: str
) -> list[dto.VersionOutputDTO]:
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        versions = repo.list_versions(project.id)
    return [dto.VersionOutputDTO.from_summary(v) for v in versions]


def get_version(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, project_id: str, version_id: str
) -> dto.VersionDetailOutputDTO:
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        version = repo.get_version(project.id, _version_id(version_id))
    return dto.VersionDetailOutputDTO.from_version(version)


def restore_version(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, project_id: str, version_id: str
) -> dto.ProjectDetailOutputDTO:
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        version = repo.get_version(project.id, _version_id(version_id))
        project.restore(version=version)
        repo.update(project)
    return dto.ProjectDetailOutputDTO.from_entity_and_content(project, version.content.data)


def freeze_version(
    *, uow: unit_of_work.UnitOfWork, owner_id: str, project_id: str, version_id: str | None
) -> dto.FrozenVersionOutputDTO:
    """Bloquea una versión del proyecto (la actual si `version_id` es `None`) para que una
    entrega la referencie. Idempotente. Sólo el dueño del proyecto."""
    with uow.transaction():
        repo = _repo(uow)
        project = _get_accessible(repo, owner_id, project_id)
        target = project.head.id if version_id is None else _version_id(version_id)
        version = repo.get_version(project.id, target)
        summary = project.freeze(version=version)
        repo.update(project)
    return dto.FrozenVersionOutputDTO(
        project_id=str(project.id),
        project_name=project.name.value,
        version_id=str(summary.id),
        n=summary.n,
        size=summary.size,
    )


def get_frozen_version(
    *, uow: unit_of_work.UnitOfWork, version_id: str
) -> dto.FrozenContentOutputDTO:
    """Contenido de una versión BLOQUEADA, sin comprobar el dueño: lo usa la revisión de
    entregas, que ya autorizó al lector en `teaching`. Una versión no bloqueada ⇒ 404, así
    esta puerta no sirve para leer proyectos ajenos en curso."""
    with uow.transaction():
        repo = _repo(uow)
        version = repo.get_version_by_id(_version_id(version_id))
        if not version.locked:
            raise exceptions.VersionNotFrozenError()
        project = repo.get(version.project_id)
    return dto.FrozenContentOutputDTO(
        project_id=str(project.id),
        project_name=project.name.value,
        version_id=str(version.id),
        n=version.n,
        size=version.content.size,
        content=version.content.data,
    )


def _get_accessible(
    repo: repository.DefaultProjectRepository, owner_id: str, project_id: str
) -> aggregate.Project:
    parsed = _uuid(project_id)
    if parsed is None:
        raise exceptions.ProjectNotFoundError()
    project = repo.get(value_objects.ProjectId(value=parsed))
    project.ensure_accessible_by(_owner(owner_id))
    return project


def _owner(owner_id: str) -> value_objects.OwnerId:
    parsed = _uuid(owner_id)
    if parsed is None:
        raise exceptions.ProjectNotFoundError()
    return value_objects.OwnerId(value=parsed)


def _version_id(raw: str) -> value_objects.ProjectVersionId:
    parsed = _uuid(raw)
    if parsed is None:
        raise exceptions.ProjectVersionNotFoundError()
    return value_objects.ProjectVersionId(value=parsed)


def _module(raw: str) -> value_objects.Module:
    try:
        return value_objects.Module(raw)
    except ValueError as exc:
        raise commons_exceptions.ValidationError(
            f"Módulo desconocido: {raw}.", code="validation_error", details={"field": "module"}
        ) from exc


def _uuid(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultProjectRepository:
    return typing.cast(repository.DefaultProjectRepository, uow.repo(aggregate.Project))
