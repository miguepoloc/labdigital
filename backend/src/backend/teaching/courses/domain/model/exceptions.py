from backend.commons.domain import exceptions


class CourseNotFoundError(exceptions.NotFoundError):
    """También para cursos con los que el usuario no tiene relación: no se revela que existen."""

    def __init__(self) -> None:
        super().__init__("Curso no encontrado.", code="not_found")


class InvalidJoinCodeError(exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__("No hay ningún curso abierto con ese código.", code="not_found")


class MembershipNotFoundError(exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__("Esa persona no está en el curso.", code="not_found")


class NotCourseTeacherError(exceptions.ForbiddenError):
    def __init__(self) -> None:
        super().__init__("Sólo el docente del curso puede hacer esto.", code="forbidden")


class CourseArchivedError(exceptions.ConflictError):
    def __init__(self) -> None:
        super().__init__("El curso está archivado.", code="course_archived")


class InvalidMembershipTransitionError(exceptions.ConflictError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_transition")
