"""Puertos SÍNCRONOS de `teaching` hacia otros productos (ARCHITECTURE.md §10.2b).

`teaching` no importa `identity`, `projects` ni `files` (contrato import-linter de
independencia). Lo que necesita de ellos lo pide por estos puertos; los adaptadores viven en
`backend.orchestrators.ports` (el único lugar que conoce todos los productos) y la raíz de
composición web los inyecta (`app.dependency_overrides`). Cada adaptador usa su PROPIA
unidad de trabajo: transacciones separadas por producto, nunca una compartida (§10.3)."""

import abc
from typing import Any

from backend.commons.domain import value_objects


class Person(value_objects.ValueObject):
    id: str
    full_name: str
    email: str


class UserDirectory(abc.ABC):
    @abc.abstractmethod
    def people(self, user_ids: list[str]) -> dict[str, Person]:
        """Nombres y correos de los ids que existan (los que no, no aparecen)."""


class FrozenVersion(value_objects.ValueObject):
    project_id: str
    project_name: str
    version_id: str
    version_n: int


class ProjectsPort(abc.ABC):
    @abc.abstractmethod
    def freeze(self, *, owner_id: str, project_id: str, version_id: str | None) -> FrozenVersion:
        """Bloquea la versión (la actual si `version_id` es `None`) del proyecto del dueño;
        404 si el proyecto no es suyo. Idempotente."""

    @abc.abstractmethod
    def frozen_content(self, *, version_id: str) -> dict[str, Any]:
        """Contenido de una versión bloqueada (404 si no lo está)."""


class StoredFile(value_objects.ValueObject):
    id: str
    owner_id: str
    kind: str
    name: str
    size: int
    mime: str


class FilesPort(abc.ABC):
    @abc.abstractmethod
    def describe(self, file_ids: list[str]) -> list[StoredFile]:
        """Metadatos de archivos subidos; 404 si alguno no existe."""
