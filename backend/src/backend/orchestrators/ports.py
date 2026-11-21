"""Adaptadores de los puertos entre productos (ARCHITECTURE.md §10.2b/§10.3).

Único sitio que conoce a la vez `identity`, `projects`, `files` y `teaching`: cada adaptador
llama a los SERVICIOS públicos del otro producto con su PROPIA unidad de trabajo
(transacciones separadas, nunca una compartida entre productos). La raíz de composición web
(`backend.entrypoints.web.app`) los inyecta con `dependency_overrides`."""

from typing import Any

from backend.commons.adapters import unit_of_work
from backend.files.blobs.domain.model import ports as files_ports
from backend.files.blobs.services import blobs
from backend.identity.users.services import users
from backend.projects.projects.services import projects
from backend.teaching.commons import ports as teaching_ports
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.services import submissions_orchestrator


class IdentityUserDirectory(teaching_ports.UserDirectory):
    def people(self, user_ids: list[str]) -> dict[str, teaching_ports.Person]:
        if not user_ids:
            return {}
        found = users.get_people(uow=unit_of_work.build(), user_ids=user_ids)
        return {
            p.id: teaching_ports.Person(id=p.id, full_name=p.full_name, email=p.email)
            for p in found
        }


class ProjectsAdapter(teaching_ports.ProjectsPort):
    def freeze(
        self, *, owner_id: str, project_id: str, version_id: str | None
    ) -> teaching_ports.FrozenVersion:
        frozen = projects.freeze_version(
            uow=unit_of_work.build(),
            owner_id=owner_id,
            project_id=project_id,
            version_id=version_id,
        )
        return teaching_ports.FrozenVersion(
            project_id=frozen.project_id,
            project_name=frozen.project_name,
            version_id=frozen.version_id,
            version_n=frozen.n,
        )

    def frozen_content(self, *, version_id: str) -> dict[str, Any]:
        return projects.get_frozen_version(uow=unit_of_work.build(), version_id=version_id).content


class FilesAdapter(teaching_ports.FilesPort):
    def describe(self, file_ids: list[str]) -> list[teaching_ports.StoredFile]:
        return [
            teaching_ports.StoredFile(
                id=b.id, owner_id=b.owner_id, kind=b.kind, name=b.name, size=b.size, mime=b.mime
            )
            for b in blobs.describe(uow=unit_of_work.build(), blob_ids=file_ids)
        ]


class TeachingBlobAccessPolicy(files_ports.BlobAccessPolicy):
    def can_view(self, *, user_id: str, is_admin: bool, blob_id: str) -> bool:
        viewer_ref = teaching_value_objects.UserRef.parse(user_id)
        if viewer_ref is None:
            return False
        return submissions_orchestrator.can_view_blob(
            uow=unit_of_work.build(),
            viewer=teaching_value_objects.Viewer(user_id=viewer_ref, is_admin=is_admin),
            blob_id=blob_id,
        )
