import uuid

import sqlalchemy as sa
from sqlalchemy import orm as sa_orm

from backend.commons.adapters import repository_helpers, unit_of_work
from backend.commons.domain import repositories
from backend.commons.domain import value_objects as base_value_objects
from backend.files.blobs.adapters import orm
from backend.files.blobs.domain.model import aggregate, exceptions, value_objects


def _to_entity(row: orm.BlobOrm) -> aggregate.Blob:
    return aggregate.Blob(
        id=value_objects.BlobId(value=row.id),
        owner_id=value_objects.OwnerId(value=row.owner_id),
        sha256=row.sha256,
        size=row.size,
        mime=row.mime,
        kind=value_objects.FileKind(row.kind),
        name=value_objects.FileName(value=row.name),
        created_at=base_value_objects.PosixTime(microseconds=row.created_at),
        updated_at=base_value_objects.PosixTime(microseconds=row.updated_at),
    )


class DefaultBlobRepository(repositories.Repository[aggregate.Blob]):
    def __init__(self, session: sa_orm.Session) -> None:
        self._session = session

    def get(self, id: value_objects.BlobId) -> aggregate.Blob:  # noqa: A002
        row = self._session.get(orm.BlobOrm, id.value)
        if row is None:
            raise exceptions.BlobNotFoundError()
        return _to_entity(row)

    def list_by_ids(self, ids: list[uuid.UUID]) -> list[aggregate.Blob]:
        if not ids:
            return []
        rows = self._session.scalars(sa.select(orm.BlobOrm).where(orm.BlobOrm.id.in_(ids)))
        return [_to_entity(r) for r in rows]

    def add(self, blob: aggregate.Blob) -> None:
        self._session.add(
            orm.BlobOrm(
                id=blob.id.value,
                owner_id=blob.owner_id.value,
                sha256=blob.sha256,
                size=blob.size,
                mime=blob.mime,
                kind=blob.kind.value,
                name=blob.name.value,
                created_at=blob.created_at.microseconds,
                updated_at=blob.updated_at.microseconds,
            )
        )
        self._session.flush()
        repository_helpers.publish_events(self._session, blob)

    def update(self, blob: aggregate.Blob) -> None:
        raise NotImplementedError("Los blobs son inmutables.")

    def delete(self, id: value_objects.BlobId) -> None:  # noqa: A002
        row = self._session.get(orm.BlobOrm, id.value)
        if row is not None:
            self._session.delete(row)


unit_of_work.register_repo(aggregate.Blob, DefaultBlobRepository)
