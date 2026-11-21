"""Vocabulario compartido por los subcontextos de `identity` (ARCHITECTURE.md §3.2):
`users` y `sessions` necesitan ambos el id del usuario, sin importarse entre sí."""

import enum

from backend.commons.domain import value_objects


class UserId(value_objects.UuidV7Id):
    """UUIDv7 (contrato §2: `sub` es el id del usuario en UUIDv7) — no `HumanFriendlyId`
    como en el template: el id viaja en el JWT y en cabeceras hacia los módulos, no en
    pantallas de soporte."""


class Role(enum.StrEnum):
    ADMIN = enum.auto()
    USER = enum.auto()
