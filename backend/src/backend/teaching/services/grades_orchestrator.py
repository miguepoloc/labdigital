"""`GET /courses/{id}/grades.csv` (LD-6): una fila por estudiante activo y una columna por
lab (en orden de creación), con la ÚLTIMA nota (la de la revisión con nota más reciente de
cualquiera de sus entregas de ese lab, individual o de equipo según quién era integrante al
entregar).

Formato pensado para Excel en es-CO: UTF-8 **con BOM**, separador `;`, **coma decimal**
(`4,5`), fin de línea CRLF, primera fila de cabecera `Nombre;Correo;<lab 1>;…`. Escala
`pass_fail`: `Aprobado`/`No aprobado`. Sin nota: celda vacía. Las celdas que empiezan por
`= + - @` (inyección de fórmulas) se prefijan con `'`."""

import csv
import io

from backend.commons.adapters import unit_of_work
from backend.teaching.commons import ports
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.services import courses
from backend.teaching.labs.services import labs
from backend.teaching.services import _access
from backend.teaching.submissions.services import submissions

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def export_csv(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
    course_id: str,
) -> tuple[str, bytes]:
    """Devuelve (nombre de archivo sugerido, bytes del CSV)."""
    access = _access.course(uow, viewer, course_id)
    _access.require_manage(access)
    course = courses.get_course(uow=uow, viewer=viewer, course_id=course_id)
    course_labs = labs.list_labs(uow=uow, course_id=access.course_id, published_only=False)
    student_ids = courses.list_active_student_ids(uow=uow, course_id=access.course_id)
    records = submissions.list_for_course(uow=uow, course_id=access.course_id)

    # (alumno, lab) -> (instante de la revisión, nota)
    latest: dict[tuple[str, str], tuple[str, float]] = {}
    for record in records:
        for review in record.reviews:
            if review.grade is None:
                continue
            for member in record.member_ids:
                key = (member, record.lab_id)
                if key not in latest or latest[key][0] <= review.created_at:
                    latest[key] = (review.created_at, review.grade)

    people = directory.people(student_ids)
    rows = sorted(
        student_ids,
        key=lambda s: (people[s].full_name.lower() if s in people else "", s),
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["Nombre", "Correo", *(_safe(lab.title) for lab in course_labs)])
    for student in rows:
        person = people.get(student)
        cells = [
            _safe(person.full_name if person else student),
            _safe(person.email if person else ""),
        ]
        for lab in course_labs:
            found = latest.get((student, lab.id))
            cells.append("" if found is None else _format(found[1], lab.grade_scale))
        writer.writerow(cells)
    filename = f"notas-{_slug(course.name)}-{_slug(course.period)}.csv"
    return filename, ("﻿" + buffer.getvalue()).encode("utf-8")


def _format(grade: float, scale: dict[str, object]) -> str:
    if scale.get("type") == teaching_value_objects.GradeScaleType.PASS_FAIL.value:
        return "Aprobado" if grade == 1 else "No aprobado"
    decimals = scale.get("decimals")
    places = decimals if isinstance(decimals, int) else 2
    return f"{grade:.{places}f}".replace(".", ",")


def _safe(value: str) -> str:
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def _slug(value: str) -> str:
    cleaned = "".join(c if c.isalnum() else "-" for c in value.lower())
    return "-".join(part for part in cleaned.split("-") if part)[:60] or "curso"
