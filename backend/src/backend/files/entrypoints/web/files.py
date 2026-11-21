"""`/v1/files` — contrato §4 "Archivos". LD-6.

`POST /files` (multipart: `file`, `kind`) admite hasta 25 MB por archivo
(`BodySizeLimitMiddleware` sube su límite sólo para esta ruta). `GET /files/{id}` sirve el
contenido si el usuario es el dueño, admin, o `BlobAccessPolicy` (docente del curso de una
entrega que lo usa / integrante) lo permite; si no, 404."""

from typing import Annotated
from urllib import parse

import fastapi
from fastapi import responses, status

from backend.commons.adapters import settings, unit_of_work
from backend.commons.adapters.api import auth as api_auth
from backend.commons.domain import audit
from backend.files.blobs.adapters import storage as storage_adapter
from backend.files.blobs.domain.model import ports
from backend.files.blobs.services import blobs, dto

router = fastapi.APIRouter(prefix="/files", tags=["files"])


def get_uow() -> unit_of_work.UnitOfWork:
    return unit_of_work.build()


def get_storage() -> ports.BlobStorage:
    return storage_adapter.FilesystemBlobStorage(settings.get_settings().blob_dir)


def get_access_policy() -> ports.BlobAccessPolicy:
    raise RuntimeError("BlobAccessPolicy sin cablear (ver backend.entrypoints.web.app).")


UowDep = Annotated[unit_of_work.UnitOfWork, fastapi.Depends(get_uow)]
StorageDep = Annotated[ports.BlobStorage, fastapi.Depends(get_storage)]
PolicyDep = Annotated[ports.BlobAccessPolicy, fastapi.Depends(get_access_policy)]


@router.post("", response_model=dto.BlobOutputDTO, status_code=status.HTTP_201_CREATED)
def upload_file(
    claims: api_auth.ClaimsDep,
    uow: UowDep,
    storage: StorageDep,
    file: Annotated[fastapi.UploadFile, fastapi.File()],
    kind: Annotated[str, fastapi.Form(max_length=20)] = "attachment",
) -> dto.BlobOutputDTO:
    return blobs.upload(
        uow=uow,
        storage=storage,
        actor=audit.Actor(id=claims.user_id, label=claims.email),
        owner_id=claims.user_id,
        filename=file.filename or "",
        kind=kind,
        stream=file.file,
    )


@router.get("/{blob_id}", response_class=responses.FileResponse)
def download_file(
    blob_id: str,
    claims: api_auth.ClaimsDep,
    uow: UowDep,
    storage: StorageDep,
    policy: PolicyDep,
) -> responses.FileResponse:
    found = blobs.get_for_download(
        uow=uow,
        storage=storage,
        policy=policy,
        user_id=claims.user_id,
        is_admin=claims.role == "admin",
        blob_id=blob_id,
    )
    return responses.FileResponse(
        found.path,
        media_type=found.mime,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{parse.quote(found.name)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
