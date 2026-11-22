"""Raíz de composición web de `teaching`: UoW por petición, `Viewer`/`Actor` desde el
access verificado y los puertos hacia otros productos.

Los puertos NO se construyen aquí (eso obligaría a importar `identity`/`projects`/`files`):
estas funciones fallan si nadie las sustituye, y `backend.entrypoints.web.app` las cambia
por los adaptadores de `backend.orchestrators.ports` (`app.dependency_overrides`)."""

from typing import Annotated

import fastapi

from backend.commons.adapters import unit_of_work
from backend.commons.adapters.api import auth as api_auth
from backend.commons.domain import audit
from backend.teaching.commons import ports
from backend.teaching.commons import value_objects as teaching_value_objects


def get_uow() -> unit_of_work.UnitOfWork:
    return unit_of_work.build()


def get_viewer(claims: api_auth.ClaimsDep) -> teaching_value_objects.Viewer:
    user = teaching_value_objects.UserRef.parse(claims.user_id)
    if user is None:
        raise api_auth.NotAuthenticatedError()
    return teaching_value_objects.Viewer(user_id=user, is_admin=claims.role == "admin")


def get_actor(claims: api_auth.ClaimsDep) -> audit.Actor:
    return audit.Actor(id=claims.user_id, label=claims.email)


def get_user_directory() -> ports.UserDirectory:
    raise RuntimeError("UserDirectory sin cablear (ver backend.entrypoints.web.app).")


def get_projects_port() -> ports.ProjectsPort:
    raise RuntimeError("ProjectsPort sin cablear (ver backend.entrypoints.web.app).")


def get_files_port() -> ports.FilesPort:
    raise RuntimeError("FilesPort sin cablear (ver backend.entrypoints.web.app).")


UowDep = Annotated[unit_of_work.UnitOfWork, fastapi.Depends(get_uow)]
ViewerDep = Annotated[teaching_value_objects.Viewer, fastapi.Depends(get_viewer)]
ActorDep = Annotated[audit.Actor, fastapi.Depends(get_actor)]
DirectoryDep = Annotated[ports.UserDirectory, fastapi.Depends(get_user_directory)]
ProjectsDep = Annotated[ports.ProjectsPort, fastapi.Depends(get_projects_port)]
FilesDep = Annotated[ports.FilesPort, fastapi.Depends(get_files_port)]
