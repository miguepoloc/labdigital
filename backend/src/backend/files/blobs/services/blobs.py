"""Capa de aplicación de `files.blobs` (LD-6): subir (25 MB, extensión + firma mágica),
describir y descargar con autorización (dueño, admin o lo que diga `BlobAccessPolicy`)."""

import typing
from typing import BinaryIO
import uuid

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import exceptions as commons_exceptions
from backend.files.blobs.adapters import repository
from backend.files.blobs.domain.model import aggregate, exceptions, ports, value_objects
from backend.files.blobs.services import dto


def upload(
    *,
    uow: unit_of_work.UnitOfWork,
    storage: ports.BlobStorage,
    actor: audit.Actor,
    owner_id: str,
    filename: str,
    kind: str,
    stream: BinaryIO,
) -> dto.BlobOutputDTO:
    """Valida nombre/tipo ANTES de leer el cuerpo; copia en streaming (corta al pasar de
    25 MB); comprueba la firma; y sólo entonces guarda el contenido y la fila. La escritura a
    disco ocurre fuera de la transacción (nunca I/O con una transacción abierta)."""
    try:
        file_kind = value_objects.FileKind(kind)
    except ValueError as exc:
        raise commons_exceptions.ValidationError(
            "kind debe ser report, bitstream o attachment.",
            code="validation_error",
            details={"field": "kind"},
        ) from exc
    name = value_objects.FileName(value=filename)
    file_type = value_objects.resolve_type(name, file_kind)
    received = storage.receive(stream, max_bytes=value_objects.MAX_FILE_BYTES)
    try:
        blob = aggregate.Blob.accept(
            owner_id=_owner(owner_id),
            name=name,
            kind=file_kind,
            file_type=file_type,
            sha256=received.sha256,
            size=received.size,
            head=received.head,
        )
    except Exception:
        storage.discard(received)
        raise
    storage.keep(received)
    with uow.transaction():
        uow.repo(aggregate.Blob).add(blob)
        uow.audit.add(
            audit.AuditEntry(
                actor=actor,
                action=value_objects.AuditAction.UPLOADED.value,
                aggregate_type=value_objects.AuditAggregateType.BLOB.value,
                aggregate_id=str(blob.id),
                changes={"sha256": blob.sha256, "size": blob.size, "kind": blob.kind.value},
            )
        )
    return dto.BlobOutputDTO.from_entity(blob)


def describe(*, uow: unit_of_work.UnitOfWork, blob_ids: list[str]) -> list[dto.BlobInfoDTO]:
    """Sin autorización (la decide quien llama). 404 si falta alguno."""
    parsed = [_uuid(b) for b in blob_ids]
    with uow.transaction():
        found = {b.id.value: b for b in _repo(uow).list_by_ids(parsed)}
    if len(found) != len(set(parsed)):
        raise exceptions.BlobNotFoundError()
    return [dto.BlobInfoDTO.from_entity(found[p]) for p in parsed]


def get_for_download(
    *,
    uow: unit_of_work.UnitOfWork,
    storage: ports.BlobStorage,
    policy: ports.BlobAccessPolicy,
    user_id: str,
    is_admin: bool,
    blob_id: str,
) -> dto.BlobDownloadDTO:
    with uow.transaction():
        blob = _repo(uow).get(value_objects.BlobId(value=_uuid(blob_id)))
    allowed = (
        is_admin
        or str(blob.owner_id) == user_id
        or policy.can_view(user_id=user_id, is_admin=is_admin, blob_id=str(blob.id))
    )
    if not allowed:
        raise exceptions.BlobNotFoundError()
    return dto.BlobDownloadDTO(
        path=storage.path_for(blob.sha256), mime=blob.mime, name=blob.name.value, size=blob.size
    )


def _uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise exceptions.BlobNotFoundError() from exc


def _owner(raw: str) -> value_objects.OwnerId:
    return value_objects.OwnerId(value=_uuid(raw))


def _repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultBlobRepository:
    return typing.cast(repository.DefaultBlobRepository, uow.repo(aggregate.Blob))
