from typing import Self

from backend.commons.application import dto
from backend.files.blobs.domain.model import aggregate


class BlobOutputDTO(dto.BaseDTO):
    """Respuesta de `POST /files`: `{id, sha256, size, mime}` (+ `kind`, `name`)."""

    id: str
    sha256: str
    size: int
    mime: str
    kind: str
    name: str

    @classmethod
    def from_entity(cls, blob: aggregate.Blob) -> Self:
        return cls(
            id=str(blob.id),
            sha256=blob.sha256,
            size=blob.size,
            mime=blob.mime,
            kind=blob.kind.value,
            name=blob.name.value,
        )


class BlobInfoDTO(BlobOutputDTO):
    owner_id: str

    @classmethod
    def from_entity(cls, blob: aggregate.Blob) -> Self:
        return cls(**BlobOutputDTO.from_entity(blob).model_dump(), owner_id=str(blob.owner_id))


class BlobDownloadDTO(dto.BaseDTO):
    path: str
    mime: str
    name: str
    size: int
