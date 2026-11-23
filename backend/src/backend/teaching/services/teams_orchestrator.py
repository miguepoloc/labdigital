"""Equipos (LD-5, LD-18). Estudiantes activos: crear (con `join_code`), unirse con código,
salir. Docente: crear equipos (uno con integrantes o N vacíos), renombrar, borrar (si no
tienen entregas), reasignar/mover integrantes (deben ser estudiantes activos), repartir al
azar a quienes no tienen equipo y bloquear/desbloquear. Un equipo bloqueado no admite
cambios de estudiantes (`team_locked`), sí del docente."""

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import exceptions as commons_exceptions
from backend.teaching.commons import ports
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.services import courses
from backend.teaching.labs.domain.model import exceptions as labs_exceptions
from backend.teaching.labs.services import dto as labs_dto
from backend.teaching.labs.services import labs
from backend.teaching.services import _access, dto
from backend.teaching.submissions.services import submissions


def _view(
    team: labs_dto.TeamOutputDTO,
    *,
    viewer: teaching_value_objects.Viewer,
    can_manage: bool,
    directory: ports.UserDirectory,
) -> dto.TeamViewOutputDTO:
    member_ids = team.member_ids()
    names = _access.people(directory, member_ids)
    show_code = can_manage or str(viewer.user_id) in member_ids
    return dto.TeamViewOutputDTO(
        id=team.id,
        lab_id=team.lab_id,
        name=team.name,
        locked=team.locked,
        members=[names[m] for m in member_ids],
        join_code=team.join_code if show_code else None,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


def _student_lab(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, lab_id: str
) -> labs_dto.LabOutputDTO:
    lab, access = _access.lab(uow, viewer, lab_id)
    _access.require_active_student(access)
    _access.require_open(access)
    if not lab.published:
        raise labs_exceptions.LabNotFoundError()
    return lab


def _team_access(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, team_id: str
) -> tuple[labs_dto.TeamOutputDTO, bool, bool]:
    """(equipo, puede gestionar, es estudiante activo); 404 si no se ve el lab."""
    team = labs.get_team(uow=uow, team_id=team_id)
    try:
        _, access = _access.lab(uow, viewer, team.lab_id)
    except labs_exceptions.LabNotFoundError as exc:
        raise labs_exceptions.TeamNotFoundError() from exc
    _access.require_open(access)
    return team, access.can_manage, access.is_active_student


def list_teams(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
    lab_id: str,
) -> list[dto.TeamViewOutputDTO]:
    _, access = _access.lab(uow, viewer, lab_id)
    if not access.can_manage:
        _access.require_active_student(access)
    return [
        _view(t, viewer=viewer, can_manage=access.can_manage, directory=directory)
        for t in labs.list_teams(uow=uow, lab_id=lab_id)
    ]


def create_team(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    lab_id: str,
    name: str,
    member_ids: list[str] | None = None,
) -> dto.TeamViewOutputDTO:
    """Quien gestiona el lab crea un equipo del docente (sin entrar él) con `member_ids`
    opcionales; un estudiante crea el suyo y entra (no puede elegir integrantes: 403)."""
    _, access = _access.lab(uow, viewer, lab_id)
    if access.can_manage:
        return _create_as_teacher(
            uow,
            viewer=viewer,
            actor=actor,
            directory=directory,
            lab_id=lab_id,
            name=name,
            member_ids=member_ids or [],
        )
    if member_ids:
        _access.require_manage(access)
    lab = _student_lab(uow, viewer, lab_id)
    team = labs.create_team(uow=uow, lab_id=lab.id, user_id=str(viewer.user_id), name=name)
    return _view(team, viewer=viewer, can_manage=False, directory=directory)


def _create_as_teacher(
    uow: unit_of_work.UnitOfWork,
    *,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    lab_id: str,
    name: str,
    member_ids: list[str],
) -> dto.TeamViewOutputDTO:
    lab = _managed_lab(uow, viewer, lab_id)
    _ensure_active_students(uow, lab.course_id, member_ids)
    team = labs.create_team_by_teacher(
        uow=uow, lab_id=lab.id, name=name, member_ids=member_ids, actor=actor
    )
    return _view(team, viewer=viewer, can_manage=True, directory=directory)


def create_teams_bulk(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    lab_id: str,
    prefix: str,
    count: int,
) -> list[dto.TeamViewOutputDTO]:
    lab = _managed_lab(uow, viewer, lab_id)
    created = labs.create_teams_bulk(
        uow=uow, lab_id=lab.id, prefix=prefix, count=count, actor=actor
    )
    return [_view(t, viewer=viewer, can_manage=True, directory=directory) for t in created]


def list_unassigned(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
    lab_id: str,
) -> list[dto.PersonOutputDTO]:
    """Estudiantes activos del curso sin equipo en el lab, por nombre."""
    lab, access = _access.lab(uow, viewer, lab_id)
    _access.require_manage(access)
    pending = _unassigned_ids(uow, lab)
    people = _access.people(directory, pending)
    return sorted((people[i] for i in pending), key=lambda p: (p.full_name.casefold(), p.id))


def auto_assign(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    lab_id: str,
) -> list[dto.TeamViewOutputDTO]:
    lab = _managed_lab(uow, viewer, lab_id)
    teams = labs.auto_assign(
        uow=uow, lab_id=lab.id, student_ids=_unassigned_ids(uow, lab), actor=actor
    )
    return [_view(t, viewer=viewer, can_manage=True, directory=directory) for t in teams]


def rename_team(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    team_id: str,
    name: str,
) -> dto.TeamViewOutputDTO:
    team = _managed_team(uow, viewer, team_id)
    renamed = labs.rename_team(uow=uow, team_id=team.id, name=name, actor=actor)
    return _view(renamed, viewer=viewer, can_manage=True, directory=directory)


def delete_team(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    team_id: str,
) -> None:
    """Con entregas ⇒ 409 `team_has_submissions` (el historial se conserva intacto)."""
    team = _managed_team(uow, viewer, team_id)
    latest = submissions.latest_for_owner(
        uow=uow, lab_id=team.lab_id, student_id=None, team_id=team.id
    )
    if latest is not None:
        raise labs_exceptions.TeamHasSubmissionsError()
    labs.delete_team(uow=uow, team_id=team.id, actor=actor)


def join_team(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
    lab_id: str,
    code: str,
) -> dto.TeamViewOutputDTO:
    lab = _student_lab(uow, viewer, lab_id)
    team = labs.join_team(uow=uow, lab_id=lab.id, user_id=str(viewer.user_id), code=code)
    return _view(team, viewer=viewer, can_manage=False, directory=directory)


def leave_team(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    directory: ports.UserDirectory,
    team_id: str,
) -> dto.TeamViewOutputDTO:
    team, _, is_student = _team_access(uow, viewer, team_id)
    if not is_student:
        raise labs_exceptions.NotInTeamError()
    left = labs.leave_team(uow=uow, team_id=team.id, user_id=str(viewer.user_id))
    return _view(left, viewer=viewer, can_manage=False, directory=directory)


def set_members(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    team_id: str,
    member_ids: list[str],
) -> dto.TeamViewOutputDTO:
    """Reemplaza los integrantes; quien estuviera en otro equipo del lab se MUEVE aquí en
    la misma transacción. Las entregas previas conservan su foto de integrantes."""
    team = _managed_team(uow, viewer, team_id)
    _ensure_active_students(uow, _course_of(uow, team), member_ids)
    updated = labs.set_team_members(uow=uow, team_id=team.id, member_ids=member_ids, actor=actor)
    return _view(updated, viewer=viewer, can_manage=True, directory=directory)


def set_locked(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    directory: ports.UserDirectory,
    team_id: str,
    locked: bool,
) -> dto.TeamViewOutputDTO:
    team = _managed_team(uow, viewer, team_id)
    updated = labs.lock_team(uow=uow, team_id=team.id, locked=locked, actor=actor)
    return _view(updated, viewer=viewer, can_manage=True, directory=directory)


def _managed_lab(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, lab_id: str
) -> labs_dto.LabOutputDTO:
    lab, access = _access.lab(uow, viewer, lab_id)
    _access.require_manage(access)
    _access.require_open(access)
    return lab


def _managed_team(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, team_id: str
) -> labs_dto.TeamOutputDTO:
    team, can_manage, _ = _team_access(uow, viewer, team_id)
    if not can_manage:
        _access.require_manage(_access.course(uow, viewer, _course_of(uow, team)))
    return team


def _ensure_active_students(
    uow: unit_of_work.UnitOfWork, course_id: str, member_ids: list[str]
) -> None:
    students = set(courses.list_active_student_ids(uow=uow, course_id=course_id))
    unknown = [m for m in member_ids if m not in students]
    if unknown:
        raise commons_exceptions.ValidationError(
            "Sólo se pueden asignar estudiantes activos del curso.",
            code="validation_error",
            details={
                "fields": {"members": "Sólo estudiantes activos del curso."},
                "invalid": unknown,
            },
        )


def _unassigned_ids(uow: unit_of_work.UnitOfWork, lab: labs_dto.LabOutputDTO) -> list[str]:
    assigned = {m for t in labs.list_teams(uow=uow, lab_id=lab.id) for m in t.member_ids()}
    students = courses.list_active_student_ids(uow=uow, course_id=lab.course_id)
    return [s for s in students if s not in assigned]


def _course_of(uow: unit_of_work.UnitOfWork, team: labs_dto.TeamOutputDTO) -> str:
    return labs.get_lab(uow=uow, lab_id=team.lab_id).course_id
