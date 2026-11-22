"""Puertos de `files.blobs`: almacenamiento de contenido y política de acceso de terceros."""

import abc
from typing import BinaryIO

from backend.commons.domain import value_objects


class ReceivedContent(value_objects.ValueObject):
    """Contenido ya escrito en un temporal, con su hash, tamaño y primeros bytes."""

    temp_ref: str
    sha256: str
    size: int
    head: bytes


class BlobStorage(abc.ABC):
    """Contenido direccionado por SHA-256 (dos subidas iguales comparten fichero)."""

    @abc.abstractmethod
    def receive(self, stream: BinaryIO, *, max_bytes: int) -> ReceivedContent:
        """Copia en streaming a un temporal calculando el hash. Si supera `max_bytes` borra
        el temporal y lanza `FileTooLargeError`."""

    @abc.abstractmethod
    def keep(self, received: ReceivedContent) -> None:
        """Mueve el temporal a su ruta definitiva (o lo descarta si ya existía)."""

    @abc.abstractmethod
    def discard(self, received: ReceivedContent) -> None: ...

    @abc.abstractmethod
    def path_for(self, sha256: str) -> str: ...


class BlobAccessPolicy(abc.ABC):
    """¿Puede alguien que NO es el dueño ver este archivo? (lo decide `teaching`: docente
    del curso de una entrega que lo usa, o integrante de esa entrega)."""

    @abc.abstractmethod
    def can_view(self, *, user_id: str, is_admin: bool, blob_id: str) -> bool: ...
