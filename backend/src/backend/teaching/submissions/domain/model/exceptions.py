from backend.commons.domain import exceptions


class SubmissionNotFoundError(exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__("Entrega no encontrada.", code="not_found")


class ResubmissionNotAllowedError(exceptions.ConflictError):
    def __init__(self) -> None:
        super().__init__(
            "Ya entregaste este laboratorio y no admite re-entregas (salvo que el docente "
            "la devuelva para corregir).",
            code="resubmission_not_allowed",
        )


class SubmissionTooLargeError(exceptions.PayloadTooLargeError):
    def __init__(self) -> None:
        super().__init__("Los archivos de la entrega superan 100 MB en total.")


class TooManyFilesError(exceptions.ValidationError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            f"Una entrega admite como máximo {limit} archivos.",
            code="validation_error",
            details={"field": "file_ids"},
        )


class EmptyReviewError(exceptions.ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "La revisión debe tener una nota, un comentario o devolver la entrega.",
            code="validation_error",
            details={"field": "comment"},
        )
