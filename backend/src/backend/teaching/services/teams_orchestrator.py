"""Equipos (LD-5). Estudiantes activos: crear (con `join_code`), unirse con código, salir.
Docente: reasignar integrantes (deben ser estudiantes activos) y bloquear/desbloquear. Un
equipo bloqueado no admite cambios de estudiantes (`team_locked`)."""

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
    directory: ports.UserDirectory,
    lab_id: str,
    name: str,
) -> dto.TeamViewOutputDTO:
    lab = _student_lab(uow, viewer, lab_id)
    team = labs.create_team(uow=uow, lab_id=lab.id, user_id=str(viewer.user_id), name=name)
    return _view(team, viewer=viewer, can_manage=False, directory=directory)


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
    team, can_manage, _ = _team_access(uow, viewer, team_id)
    if not can_manage:
        _access.require_manage(_access.course(uow, viewer, _course_of(uow, team)))
    lab = labs.get_lab(uow=uow, lab_id=team.lab_id)
    students = set(courses.list_active_student_ids(uow=uow, course_id=lab.course_id))
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
    team, can_manage, _ = _team_access(uow, viewer, team_id)
    if not can_manage:
        _access.require_manage(_access.course(uow, viewer, _course_of(uow, team)))
    updated = labs.lock_team(uow=uow, team_id=team.id, locked=locked, actor=actor)
    return _view(updated, viewer=viewer, can_manage=True, directory=directory)


def _course_of(uow: unit_of_work.UnitOfWork, team: labs_dto.TeamOutputDTO) -> str:
    return labs.get_lab(uow=uow, lab_id=team.lab_id).course_id
