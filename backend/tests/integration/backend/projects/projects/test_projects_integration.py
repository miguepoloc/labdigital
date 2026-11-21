import datetime
import uuid

import pytest
import sqlalchemy as sa
import time_machine

from backend.commons.adapters import unit_of_work
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users
from backend.projects.projects.adapters import orm
from backend.projects.projects.domain.model import exceptions
from backend.projects.projects.services import dto, projects
from tests.unit.backend.identity import builders
from tests.unit.backend.projects.projects import test_projects as unit_projects

pytestmark = pytest.mark.integration


def _owner(uow: unit_of_work.UnitOfWork) -> str:
    users.register(
        uow=uow,
        input_dto=users_dto.RegisterInputDTO(
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            full_name="Dueño",
            password="caballo-bateria-grapa",
            accept_data_policy=True,
        ),
        config=builders.CONFIG,
        context=builders.CONTEXT,
    )
    with uow.transaction():
        return str(
            uow.session.execute(
                sa.text("SELECT id FROM users ORDER BY created_at DESC LIMIT 1")
            ).scalar_one()
        )


def test_versions_persist_with_deferred_fk_and_content(db: sa.Engine) -> None:
    uow = unit_of_work.build()
    owner = _owner(uow)
    project = projects.create_project(
        uow=uow,
        owner_id=owner,
        input_dto=dto.CreateProjectInputDTO(
            name="Semáforo", module="fpga", content=unit_projects.content("v1")
        ),
    )
    projects.autosave(
        uow=uow,
        owner_id=owner,
        project_id=project.id,
        input_dto=dto.AutosaveInputDTO(content=unit_projects.content("v1b"), base_version=1),
    )
    with time_machine.travel(
        datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(minutes=11)
    ):
        saved = projects.autosave(
            uow=uow,
            owner_id=owner,
            project_id=project.id,
            input_dto=dto.AutosaveInputDTO(content=unit_projects.content("v2"), base_version=1),
        )
    assert saved.n == 2
    with pytest.raises(exceptions.VersionConflictError):
        projects.autosave(
            uow=uow,
            owner_id=owner,
            project_id=project.id,
            input_dto=dto.AutosaveInputDTO(content=unit_projects.content("x"), base_version=1),
        )

    v1 = [
        v
        for v in projects.list_versions(uow=uow, owner_id=owner, project_id=project.id)
        if v.n == 1
    ][0]
    detail = projects.get_version(uow=uow, owner_id=owner, project_id=project.id, version_id=v1.id)
    assert detail.content["files"][0]["text"] == "v1b"  # type: ignore[index]
    restored = projects.restore_version(
        uow=uow, owner_id=owner, project_id=project.id, version_id=v1.id
    )
    assert restored.current_version.n == 3

    projects.delete_project(uow=uow, owner_id=owner, project_id=project.id)
    with db.connect() as conn:
        row = conn.execute(sa.select(orm.ProjectOrm)).one()
        sizes = conn.execute(
            sa.select(orm.ProjectVersionOrm.n, orm.ProjectVersionOrm.size).order_by(
                orm.ProjectVersionOrm.n
            )
        ).all()
    assert row.deleted_at is not None and row.last_n == 3  # borrado lógico: las versiones siguen
    assert [n for n, _ in sizes] == [1, 2, 3] and all(size > 0 for _, size in sizes)
