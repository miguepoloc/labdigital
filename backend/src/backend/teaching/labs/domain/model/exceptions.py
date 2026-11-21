from backend.commons.domain import exceptions


class LabNotFoundError(exceptions.NotFoundError):
    """También para labs no publicados vistos por un estudiante."""

    def __init__(self) -> None:
        super().__init__("Laboratorio no encontrado.", code="not_found")


class LabPublishedError(exceptions.ConflictError):
    def __init__(self, field: str) -> None:
        super().__init__(
            "Este campo ya no se puede cambiar: el laboratorio está publicado.",
            code="lab_published",
            details={"field": field},
        )


class LabNotOpenError(exceptions.ConflictError):
    def __init__(self) -> None:
        super().__init__("El laboratorio todavía no está abierto.", code="lab_not_open")


class DeadlinePassedError(exceptions.ConflictError):
    """409 `deadline_passed` (contrato §6): cierre estricto y pasó `due_at`."""

    def __init__(self) -> None:
        super().__init__("La fecha límite de entrega ya pasó.", code="deadline_passed")


class NotATeamLabError(exceptions.ConflictError):
    def __init__(self) -> None:
        super().__init__("Este laboratorio es individual: no tiene equipos.", code="not_team_lab")


class TeamNotFoundError(exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__("Equipo no encontrado.", code="not_found")


class InvalidTeamCodeError(exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__(
            "No hay ningún equipo con ese código en este laboratorio.", code="not_found"
        )


class TeamFullError(exceptions.ConflictError):
    def __init__(self, max_size: int) -> None:
        super().__init__(
            f"El equipo ya tiene el máximo de {max_size} integrantes.",
            code="team_full",
            details={"max_team_size": max_size},
        )


class TeamLockedError(exceptions.ConflictError):
    def __init__(self) -> None:
        super().__init__("El docente fijó este equipo: no admite cambios.", code="team_locked")


class AlreadyInTeamError(exceptions.ConflictError):
    def __init__(self) -> None:
        super().__init__("Ya estás en un equipo de este laboratorio.", code="already_in_team")


class NotInTeamError(exceptions.ConflictError):
    def __init__(self) -> None:
        super().__init__("No perteneces a este equipo.", code="not_in_team")


class TeamTooLargeError(exceptions.ValidationError):
    def __init__(self, max_size: int) -> None:
        super().__init__(
            f"Un equipo de este laboratorio admite como máximo {max_size} integrantes.",
            code="validation_error",
            details={"field": "members"},
        )


class TeamRequiredError(exceptions.ConflictError):
    """409 `team_required`: lab en equipo y el estudiante aún no tiene equipo."""

    def __init__(self) -> None:
        super().__init__(
            "Este laboratorio se entrega en equipo: únete a uno o créalo primero.",
            code="team_required",
        )
