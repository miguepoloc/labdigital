import datetime
import uuid

import pytest
import time_machine

from backend.commons.domain import exceptions as commons_exceptions
from backend.projects.projects.domain.model import aggregate, exceptions
from backend.projects.projects.services import dto, projects
from tests.unit import fakes
from tests.unit.backend.projects.projects import fakes as project_fakes

pytestmark = pytest.mark.unit

OWNER = str(uuid.uuid4())
OTHER = str(uuid.uuid4())


def content(text: str = "x") -> dict[str, object]:
    return {
        "format": "basys3-sim-project",
        "version": 1,
        "name": "p",
        "top": "top",
        "simTop": "tb",
        "files": [{"name": "top.vhd", "role": "src", "text": text}],
        "report": None,
    }


def _build() -> tuple[fakes.FakeUnitOfWork, project_fakes.FakeProjectRepository]:
    uow = fakes.FakeUnitOfWork()
    repo = project_fakes.FakeProjectRepository(uow.outbox)
    uow.register(aggregate.Project, repo)
    return uow, repo


def _create(uow: fakes.FakeUnitOfWork) -> dto.ProjectDetailOutputDTO:
    return projects.create_project(
        uow=uow,  # type: ignore[arg-type]
        owner_id=OWNER,
        input_dto=dto.CreateProjectInputDTO(name="Contador", module="fpga", content=content()),
    )


def _autosave(
    uow: fakes.FakeUnitOfWork, project_id: str, base: int, text: str
) -> dto.AutosaveOutputDTO:
    return projects.autosave(
        uow=uow,  # type: ignore[arg-type]
        owner_id=OWNER,
        project_id=project_id,
        input_dto=dto.AutosaveInputDTO(content=content(text), base_version=base),
    )


def test_autosave_overwrites_open_version_within_ten_minutes() -> None:
    uow, repo = _build()
    project = _create(uow)
    first = _autosave(uow, project.id, 1, "a")
    second = _autosave(uow, project.id, 1, "b")
    assert (first.version_id, first.n) == (second.version_id, 1)
    assert second.revision == first.revision + 1
    assert len(repo.versions) == 1
    detail = projects.get_project(uow=uow, owner_id=OWNER, project_id=project.id)  # type: ignore[arg-type]
    assert detail.content["files"][0]["text"] == "b"  # type: ignore[index]


def test_autosave_creates_new_version_after_ten_minutes() -> None:
    uow, repo = _build()
    project = _create(uow)
    later = datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(minutes=11)
    with time_machine.travel(later):
        result = _autosave(uow, project.id, 1, "nuevo")
    assert result.n == 2 and len(repo.versions) == 2


def test_autosave_conflict_when_base_version_is_stale() -> None:
    uow, _ = _build()
    project = _create(uow)
    projects.create_manual_version(uow=uow, owner_id=OWNER, project_id=project.id, label="v1")  # type: ignore[arg-type]
    _autosave(
        uow, project.id, 1, "a"
    )  # base 1 sigue siendo la actual (manual promovida) -> crea n=2
    with pytest.raises(exceptions.VersionConflictError) as info:
        _autosave(uow, project.id, 1, "b")
    assert info.value.code == "version_conflict"
    assert info.value.details["current_version"] == 2


def test_manual_version_promotes_autosave_then_copies_and_restore() -> None:
    uow, repo = _build()
    project = _create(uow)
    promoted = projects.create_manual_version(
        uow=uow, owner_id=OWNER, project_id=project.id, label="Entrega"
    )  # type: ignore[arg-type]
    # Devuelve `Project` (contrato §6.1) con la revision nueva.
    assert (promoted.current_version_n, promoted.revision) == (1, 2)
    assert promoted.content["format"] == "basys3-sim-project"
    copy = projects.create_manual_version(
        uow=uow, owner_id=OWNER, project_id=project.id, label=None
    )  # type: ignore[arg-type]
    assert (copy.current_version_n, copy.revision) == (2, 3)
    restored = projects.restore_version(
        uow=uow, owner_id=OWNER, project_id=project.id, version_id=promoted.current_version_id
    )  # type: ignore[arg-type]
    assert (restored.current_version_n, restored.revision) == (3, 4)
    versions = projects.list_versions(uow=uow, owner_id=OWNER, project_id=project.id)  # type: ignore[arg-type]
    assert [v.n for v in versions] == [3, 2, 1]
    assert [v.kind for v in versions] == ["manual", "manual", "manual"]
    assert versions[2].label == "Entrega" and "versión 1" in (versions[0].label or "")
    assert len(repo.versions) == 3


def test_other_owner_and_deleted_projects_are_not_found() -> None:
    uow, _ = _build()
    project = _create(uow)
    with pytest.raises(exceptions.ProjectNotFoundError):
        projects.get_project(uow=uow, owner_id=OTHER, project_id=project.id)  # type: ignore[arg-type]
    assert projects.list_projects(uow=uow, owner_id=OTHER, module=None) == []  # type: ignore[arg-type]
    projects.delete_project(uow=uow, owner_id=OWNER, project_id=project.id)  # type: ignore[arg-type]
    with pytest.raises(exceptions.ProjectNotFoundError):
        projects.get_project(uow=uow, owner_id=OWNER, project_id=project.id)  # type: ignore[arg-type]
    assert projects.list_projects(uow=uow, owner_id=OWNER, module="fpga") == []  # type: ignore[arg-type]


def test_content_validation() -> None:
    uow, _ = _build()
    with pytest.raises(commons_exceptions.ValidationError):
        projects.create_project(
            uow=uow,
            owner_id=OWNER,
            input_dto=dto.CreateProjectInputDTO(
                name="x", module="fpga", content={"format": "otro"}
            ),
        )  # type: ignore[arg-type]
    with pytest.raises(commons_exceptions.PayloadTooLargeError):
        projects.create_project(
            uow=uow,
            owner_id=OWNER,
            input_dto=dto.CreateProjectInputDTO(
                name="x", module="fpga", content=content("a" * (2 * 1024 * 1024))
            ),
        )  # type: ignore[arg-type]
    with pytest.raises(commons_exceptions.ValidationError):
        projects.create_project(
            uow=uow,
            owner_id=OWNER,
            input_dto=dto.CreateProjectInputDTO(name="x", module="arduino", content=content()),
        )  # type: ignore[arg-type]


def test_revision_rises_on_every_save_and_stale_revision_conflicts() -> None:
    uow, _ = _build()
    project = _create(uow)
    assert project.revision == 1
    first = projects.autosave(
        uow=uow,  # type: ignore[arg-type]
        owner_id=OWNER,
        project_id=project.id,
        input_dto=dto.AutosaveInputDTO(content=content("a"), base_version=1, base_revision=1),
    )
    second = _autosave(uow, project.id, 1, "b")  # sin base_revision: compatibilidad
    assert (first.n, first.revision) == (1, 2) and (second.n, second.revision) == (1, 3)
    with pytest.raises(exceptions.VersionConflictError) as info:
        projects.autosave(
            uow=uow,  # type: ignore[arg-type]
            owner_id=OWNER,
            project_id=project.id,
            input_dto=dto.AutosaveInputDTO(content=content("c"), base_version=1, base_revision=2),
        )
    assert info.value.details == {
        "current_version": 1,
        "current_revision": 3,
        "current_version_id": first.version_id,
    }
    manual = projects.create_manual_version(
        uow=uow, owner_id=OWNER, project_id=project.id, label=None
    )  # type: ignore[arg-type]
    detail = projects.get_project(uow=uow, owner_id=OWNER, project_id=project.id)  # type: ignore[arg-type]
    assert manual.current_version_n == 1 and manual.revision == detail.revision == 4


def test_frozen_version_is_never_overwritten_by_autosave() -> None:
    uow, repo = _build()
    project = _create(uow)
    _autosave(uow, project.id, 1, "entregado")
    frozen = projects.freeze_version(
        uow=uow, owner_id=OWNER, project_id=project.id, version_id=None
    )  # type: ignore[arg-type]
    assert frozen.n == 1
    again = projects.freeze_version(
        uow=uow, owner_id=OWNER, project_id=project.id, version_id=frozen.version_id
    )  # type: ignore[arg-type]
    assert again == frozen  # idempotente
    after = _autosave(uow, project.id, 1, "sigo editando")  # dentro de la ventana de 10 min
    assert after.n == 2
    kinds = {
        v.n: v.kind
        for v in projects.list_versions(uow=uow, owner_id=OWNER, project_id=project.id)  # type: ignore[arg-type]
    }
    assert kinds == {1: "submitted", 2: "autosave"}
    _autosave(uow, project.id, 2, "y más")
    content_of_frozen = projects.get_frozen_version(uow=uow, version_id=frozen.version_id)  # type: ignore[arg-type]
    assert content_of_frozen.content["files"][0]["text"] == "entregado"  # type: ignore[index]
    head = projects.get_project(uow=uow, owner_id=OWNER, project_id=project.id)  # type: ignore[arg-type]
    assert head.content["files"][0]["text"] == "y más"  # type: ignore[index]
    with pytest.raises(exceptions.VersionNotFrozenError):
        projects.get_frozen_version(uow=uow, version_id=after.version_id)  # type: ignore[arg-type]
    with pytest.raises(exceptions.ProjectNotFoundError):
        projects.freeze_version(uow=uow, owner_id=OTHER, project_id=project.id, version_id=None)  # type: ignore[arg-type]
    assert len(repo.versions) == 2
