"""Entregas y revisión (LD-6).

Entregar (`submit`), en este orden, sin transacción exterior (cada producto confirma la
suya, §10.3):
1. permisos y reglas que NO necesitan otros productos: estudiante activo, lab publicado,
   equipo (lab en equipo ⇒ `team_required` si no tiene), re-entrega permitida, plazo
   (`lab_not_open`, `deadline_passed`, `is_late`);
2. archivos: deben existir y ser del que entrega (si no, 404);
3. `projects` congela la versión (`kind=submitted`, `locked`): desde aquí el autosave ya no
   puede tocarla. Si el paso 4 fallara, la versión queda congelada sin entrega: inocuo;
4. `submissions` crea la entrega (re-comprueba la re-entrega y el intento único).

Ver una entrega: el docente del curso (o admin) o quien era integrante al entregar. Cualquier
otro ⇒ 404. Revisar: sólo docente/admin; la nota se valida contra la escala del lab."""

from typing import Any

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import exceptions as commons_exceptions
from backend.teaching.commons import ports
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.domain.model import exceptions as courses_exceptions
from backend.teaching.labs.domain.model import exceptions as labs_exceptions
from backend.teaching.labs.services import labs
from backend.teaching.services import _access, dto
from backend.teaching.submissions.domain.model import exceptions as submissions_exceptions
from backend.teaching.submissions.services import dto as submissions_dto
from backend.teaching.submissions.services import submissions

_RETURNED = "returned"


class FileNotFoundForSubmissionError(commons_exceptions.NotFoundError):
    def __init__(self) -> None:
        super().__init__("Archivo no encontrado.", code="not_found")


def submit(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    projects_port: ports.ProjectsPort,
    files_port: ports.FilesPort,
    directory: ports.UserDirectory,
    lab_id: str,
    input_dto: dto.SubmitInputDTO,
) -> dto.SubmissionOutputDTO:
    lab, access = _access.lab(uow, viewer, lab_id)
    if access.can_manage and not access.is_active_student:
        raise commons_exceptions.ForbiddenError(
            "Sólo los estudiantes entregan laboratorios.", code="forbidden"
        )
    _access.require_active_student(access)
    _access.require_open(access)
    me = str(viewer.user_id)

    team_id: str | None = None
    member_ids = [me]
    if lab.team_mode == "team":
        team = labs.find_team_of(uow=uow, lab_id=lab.id, user_id=me)
        if team is None:
            raise labs_exceptions.TeamRequiredError()
        team_id, member_ids = team.id, team.member_ids()

    previous = submissions.latest_for_owner(
        uow=uow, lab_id=lab.id, student_id=None if team_id else me, team_id=team_id
    )
    returned = previous is not None and previous.status == _RETURNED
    if previous is not None and not (lab.allow_resubmission or returned):
        raise submissions_exceptions.ResubmissionNotAllowedError()
    timing = labs.evaluate_submission(uow=uow, lab_id=lab.id, returned=returned)

    files = (
        files_port.describe(list(dict.fromkeys(input_dto.file_ids))) if input_dto.file_ids else []
    )
    if any(f.owner_id != me for f in files):
        raise FileNotFoundForSubmissionError()

    frozen = projects_port.freeze(
        owner_id=me, project_id=input_dto.project_id, version_id=input_dto.version_id
    )
    record = submissions.create_submission(
        uow=uow,
        actor=actor,
        input_dto=submissions_dto.CreateSubmissionInputDTO(
            lab_id=lab.id,
            course_id=lab.course_id,
            submitter_id=me,
            team_id=team_id,
            member_ids=member_ids,
            allow_resubmission=lab.allow_resubmission,
            is_late=timing.is_late,
            project=submissions_dto.FrozenProjectInputDTO(**frozen.model_dump()),
            files=[
                submissions_dto.FileRefInputDTO(blob_id=f.id, kind=f.kind, size=f.size, name=f.name)
                for f in files
            ],
        ),
    )
    return _detail(uow, record, projects_port, files_port, directory)


def list_for_lab(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
    lab_id: str,
) -> list[dto.SubmissionListItemOutputDTO]:
    """Docente: todas; estudiante: las suyas o de su equipo."""
    _, access = _access.lab(uow, viewer, lab_id)
    if not access.can_manage:
        _access.require_active_student(access)
    records = submissions.list_for_lab(
        uow=uow, lab_id=lab_id, member_id=None if access.can_manage else str(viewer.user_id)
    )
    names = _access.people(directory, [i for r in records for i in (r.submitter_id, *r.member_ids)])
    teams = _team_names(uow, records)
    return [_list_item(r, names, teams) for r in records]


def get_submission(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    projects_port: ports.ProjectsPort,
    files_port: ports.FilesPort,
    directory: ports.UserDirectory,
    submission_id: str,
) -> dto.SubmissionOutputDTO:
    record = _visible(uow, viewer, submission_id)
    return _detail(uow, record, projects_port, files_port, directory)


def review(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    projects_port: ports.ProjectsPort,
    files_port: ports.FilesPort,
    directory: ports.UserDirectory,
    submission_id: str,
    input_dto: dto.ReviewInputDTO,
) -> dto.SubmissionOutputDTO:
    record = _visible(uow, viewer, submission_id)
    access = _access.course(uow, viewer, record.course_id)
    _access.require_manage(access)
    lab = labs.get_lab(uow=uow, lab_id=record.lab_id)
    updated = submissions.add_review(
        uow=uow,
        submission_id=record.id,
        reviewer_id=str(viewer.user_id),
        actor=actor,
        grade_scale=teaching_value_objects.GradeScale.from_storage(lab.grade_scale),
        grade=input_dto.grade,
        comment=input_dto.comment,
        return_for_resubmission=input_dto.return_for_resubmission,
    )
    return _detail(uow, updated, projects_port, files_port, directory)


def can_view_blob(
    *, uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, blob_id: str
) -> bool:
    """¿Usa este archivo alguna entrega que el que mira puede ver? (docente del curso de la
    entrega, admin o integrante)."""
    if viewer.is_admin:
        return True
    me = str(viewer.user_id)
    for record in submissions.list_using_blob(uow=uow, blob_id=blob_id):
        if me in record.member_ids:
            return True
        try:
            if _access.course(uow, viewer, record.course_id).can_manage:
                return True
        except courses_exceptions.CourseNotFoundError:
            continue
    return False


# --------------------------------------------------------------------------------------


def _visible(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, submission_id: str
) -> submissions_dto.SubmissionRecordDTO:
    record = submissions.get_submission(uow=uow, submission_id=submission_id)
    if str(viewer.user_id) in record.member_ids:
        return record
    try:
        access = _access.course(uow, viewer, record.course_id)
    except courses_exceptions.CourseNotFoundError as exc:
        raise submissions_exceptions.SubmissionNotFoundError() from exc
    if not access.can_manage:
        raise submissions_exceptions.SubmissionNotFoundError()
    return record


def _team_names(
    uow: unit_of_work.UnitOfWork, records: list[submissions_dto.SubmissionRecordDTO]
) -> dict[str, str]:
    team_ids = {r.team_id for r in records if r.team_id}
    return {t: labs.get_team(uow=uow, team_id=t).name for t in team_ids}


def _list_item(
    record: submissions_dto.SubmissionRecordDTO,
    names: dict[str, dto.PersonOutputDTO],
    teams: dict[str, str],
) -> dto.SubmissionListItemOutputDTO:
    return dto.SubmissionListItemOutputDTO(
        **submissions_dto.SubmissionSummaryDTO.from_record(record).model_dump(),
        lab_id=record.lab_id,
        project_id=record.project_id,
        version_id=record.version_id,
        version_n=record.version_n,
        submitted_by=names[record.submitter_id],
        team=None
        if record.team_id is None
        else dto.TeamRefOutputDTO(id=record.team_id, name=teams.get(record.team_id, "")),
        members=[names[m] for m in record.member_ids],
    )


def _detail(
    uow: unit_of_work.UnitOfWork,
    record: submissions_dto.SubmissionRecordDTO,
    projects_port: ports.ProjectsPort,
    files_port: ports.FilesPort,
    directory: ports.UserDirectory,
) -> dto.SubmissionOutputDTO:
    names = _access.people(
        directory,
        [record.submitter_id, *record.member_ids, *(r.reviewer_id for r in record.reviews)],
    )
    stored = (
        {f.id: f for f in files_port.describe([f.blob_id for f in record.files])}
        if record.files
        else {}
    )
    content: dict[str, Any] = projects_port.frozen_content(version_id=record.version_id)
    item = _list_item(record, names, _team_names(uow, [record]))
    return dto.SubmissionOutputDTO(
        **item.model_dump(),
        files=[
            dto.SubmissionFileOutputDTO(
                id=f.blob_id,
                kind=f.kind,
                name=f.name,
                size=f.size,
                mime=stored[f.blob_id].mime if f.blob_id in stored else "application/octet-stream",
            )
            for f in record.files
        ],
        reviews=[
            dto.ReviewOutputDTO(
                id=r.id,
                reviewer_name=names[r.reviewer_id].full_name,
                grade=r.grade,
                comment=r.comment,
                returned_for_resubmission=r.returned_for_resubmission,
                created_at=r.created_at,
            )
            for r in record.reviews
        ],
        content=content,
    )
