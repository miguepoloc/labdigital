from backend.commons.domain import exceptions


class BlobNotFoundError(exceptions.NotFoundError):
    """También si existe pero el usuario no puede verlo (no se revela)."""

    def __init__(self) -> None:
        super().__init__("Archivo no encontrado.", code="not_found")


class FileTooLargeError(exceptions.PayloadTooLargeError):
    def __init__(self) -> None:
        super().__init__("El archivo supera 25 MB.")


class SignatureMismatchError(exceptions.ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "El contenido del archivo no corresponde a su extensión.",
            code="validation_error",
            details={"field": "file"},
        )


class EmptyFileError(exceptions.ValidationError):
    def __init__(self) -> None:
        super().__init__(
            "El archivo está vacío.", code="validation_error", details={"field": "file"}
        )
