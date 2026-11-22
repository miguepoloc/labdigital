from backend.commons.domain import exceptions


class ProjectNotFoundError(exceptions.NotFoundError):
    """También para proyectos de otro usuario o borrados: no se revela que existen."""

    def __init__(self) -> None:
        super().__init__("Proyecto no encontrado.", code="not_found")


class ProjectVersionNotFoundError(exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__("Versión no encontrada.", code="not_found")


class VersionConflictError(exceptions.ConflictError):
    """409 `version_conflict` (contrato §4/§6.1): `base_version` o `base_revision` ya no son
    los actuales. `details = {current_version, current_revision, current_version_id}`."""

    def __init__(self, *, current_n: int, current_version_id: str, current_revision: int) -> None:
        super().__init__(
            "El proyecto cambió desde otra pestaña o dispositivo. Recarga para continuar.",
            code="version_conflict",
            details={
                "current_version": current_n,
                "current_revision": current_revision,
                "current_version_id": current_version_id,
            },
        )


class VersionNotFrozenError(exceptions.NotFoundError):
    """Se pidió el contenido congelado de una versión que no está bloqueada por una entrega."""

    def __init__(self) -> None:
        super().__init__("Versión no encontrada.", code="not_found")
