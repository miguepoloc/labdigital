from backend.commons.domain import exceptions


class ProjectNotFoundError(exceptions.NotFoundError):
    """También para proyectos de otro usuario o borrados: no se revela que existen."""

    def __init__(self) -> None:
        super().__init__("Proyecto no encontrado.", code="not_found")


class ProjectVersionNotFoundError(exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__("Versión no encontrada.", code="not_found")


class VersionConflictError(exceptions.ConflictError):
    """409 `version_conflict` (contrato §4): `base_version` ya no es la versión actual."""

    def __init__(self, *, current_n: int, current_version_id: str) -> None:
        super().__init__(
            "El proyecto cambió desde otra pestaña o dispositivo. Recarga para continuar.",
            code="version_conflict",
            details={"current_version": current_n, "current_version_id": current_version_id},
        )
