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
    assert first == second and first.n == 1
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
    assert (promoted.n, promoted.kind, promoted.label) == (1, "manual", "Entrega")
    copy = projects.create_manual_version(
        uow=uow, owner_id=OWNER, project_id=project.id, label=None
    )  # type: ignore[arg-type]
    assert copy.n == 2
    restored = projects.restore_version(
        uow=uow, owner_id=OWNER, project_id=project.id, version_id=promoted.id
    )  # type: ignore[arg-type]
    assert restored.current_version.n == 3 and "versión 1" in (restored.current_version.label or "")
    assert [
        v.n for v in projects.list_versions(uow=uow, owner_id=OWNER, project_id=project.id)
    ] == [3, 2, 1]  # type: ignore[arg-type]
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
