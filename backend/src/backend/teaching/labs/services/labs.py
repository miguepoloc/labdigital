"""Capa de aplicación de `teaching.labs` (LD-5). Estas funciones NO deciden quién puede
qué: las llaman los orquestadores de `teaching.services`, que ya comprobaron la relación con
el curso (`courses.get_access`). Cada una es la única puerta a `Lab`/`Team`."""

import random
import typing
from typing import Any
import uuid

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import value_objects as base_value_objects
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.labs.adapters import repository
from backend.teaching.labs.domain.model import aggregate, exceptions, value_objects
from backend.teaching.labs.services import dto

# Reparto automático de equipos: no es criptográfico, pero así no depende de la semilla global.
_RANDOM = random.SystemRandom()
# --------------------------------------------------------------------------------------
# Labs
# --------------------------------------------------------------------------------------


def create_lab(
    *,
    uow: unit_of_work.UnitOfWork,
    course_id: str,
    created_by: str,
    actor: audit.Actor,
    input_dto: dto.LabInputDTO,
) -> dto.LabOutputDTO:
    missing = {
        name: "Campo obligatorio."
        for name in ("title", "deadline_policy", "team_mode", "grade_scale")
        if getattr(input_dto, name) is None
    }
    if missing:
        raise commons_exceptions.ValidationError(
            next(iter(missing.values())), code="validation_error", details={"fields": missing}
        )
    assert input_dto.title is not None and input_dto.grade_scale is not None
    lab = aggregate.Lab.create(
        course_id=teaching_value_objects.CourseId(value=uuid.UUID(course_id)),
        created_by=teaching_value_objects.UserRef(value=uuid.UUID(created_by)),
        title=value_objects.LabTitle(value=input_dto.title),
        statement_md=value_objects.StatementMd(value=input_dto.statement_md or ""),
        module=_module(input_dto.module or value_objects.LabModule.FPGA.value),
        schedule=_schedule(input_dto.opens_at, input_dto.due_at, input_dto.deadline_policy),
        team_setup=_team_setup(input_dto.team_mode, input_dto.max_team_size),
        grade_scale=teaching_value_objects.GradeScale.parse(input_dto.grade_scale),
        allow_resubmission=bool(input_dto.allow_resubmission),
    )
    with uow.transaction():
        uow.repo(aggregate.Lab).add(lab)
        uow.audit.add(_lab_entry(lab, value_objects.AuditAction.LAB_CREATED, actor))
    return dto.LabOutputDTO.from_entity(lab)


def get_lab(*, uow: unit_of_work.UnitOfWork, lab_id: str) -> dto.LabOutputDTO:
    with uow.transaction():
        lab = uow.repo(aggregate.Lab).get(_lab_id(lab_id))
    return dto.LabOutputDTO.from_entity(lab)


def list_labs(
    *, uow: unit_of_work.UnitOfWork, course_id: str, published_only: bool
) -> list[dto.LabOutputDTO]:
    with uow.transaction():
        labs = _labs(uow).list_for_course(
            teaching_value_objects.CourseId(value=uuid.UUID(course_id)),
            published_only=published_only,
        )
    return [dto.LabOutputDTO.from_entity(lab) for lab in labs]


def update_lab(
    *,
    uow: unit_of_work.UnitOfWork,
    lab_id: str,
    actor: audit.Actor,
    input_dto: dto.LabInputDTO,
) -> dto.LabOutputDTO:
    """PATCH: sólo cambian los campos presentes en el cuerpo (`model_fields_set`)."""
    sent = input_dto.model_fields_set
    with uow.transaction():
        repo = uow.repo(aggregate.Lab)
        lab = repo.get(_lab_id(lab_id))
        changes: dict[str, Any] = {}
        if "title" in sent:
            changes["title"] = value_objects.LabTitle(value=input_dto.title or "")
        if "statement_md" in sent:
            changes["statement_md"] = value_objects.StatementMd(value=input_dto.statement_md or "")
        if "module" in sent and input_dto.module is not None:
            changes["module"] = _module(input_dto.module)
        if sent & {"opens_at", "due_at", "deadline_policy"}:
            current = lab.schedule
            changes["schedule"] = _schedule(
                input_dto.opens_at if "opens_at" in sent else _dt(current.opens_at),
                input_dto.due_at if "due_at" in sent else _dt(current.due_at),
                input_dto.deadline_policy
                if "deadline_policy" in sent
                else current.deadline_policy.value,
            )
        if sent & {"team_mode", "max_team_size"}:
            changes["team_setup"] = _team_setup(
                input_dto.team_mode if "team_mode" in sent else lab.team_setup.team_mode.value,
                input_dto.max_team_size
                if "max_team_size" in sent
                else lab.team_setup.max_team_size,
            )
        if "grade_scale" in sent and input_dto.grade_scale is not None:
            changes["grade_scale"] = teaching_value_objects.GradeScale.parse(input_dto.grade_scale)
        if "allow_resubmission" in sent and input_dto.allow_resubmission is not None:
            changes["allow_resubmission"] = input_dto.allow_resubmission
        applied = lab.apply_changes(changes)
        if applied:
            repo.update(lab)
            uow.audit.add(_lab_entry(lab, value_objects.AuditAction.LAB_UPDATED, actor, applied))
    return dto.LabOutputDTO.from_entity(lab)


def publish_lab(
    *, uow: unit_of_work.UnitOfWork, lab_id: str, actor: audit.Actor
) -> dto.LabOutputDTO:
    with uow.transaction():
        repo = uow.repo(aggregate.Lab)
        lab = repo.get(_lab_id(lab_id))
        if lab.publish():
            repo.update(lab)
            uow.audit.add(_lab_entry(lab, value_objects.AuditAction.LAB_PUBLISHED, actor))
    return dto.LabOutputDTO.from_entity(lab)


def evaluate_submission(
    *, uow: unit_of_work.UnitOfWork, lab_id: str, returned: bool
) -> dto.SubmissionTimingOutputDTO:
    """¿Se admite una entrega ahora? (`lab_not_open`, `deadline_passed`) y `is_late`."""
    with uow.transaction():
        lab = uow.repo(aggregate.Lab).get(_lab_id(lab_id))
    is_late = lab.evaluate_submission(now=base_value_objects.PosixTime.now(), returned=returned)
    return dto.SubmissionTimingOutputDTO(is_late=is_late)


# --------------------------------------------------------------------------------------
# Equipos
# --------------------------------------------------------------------------------------


def list_teams(*, uow: unit_of_work.UnitOfWork, lab_id: str) -> list[dto.TeamOutputDTO]:
    with uow.transaction():
        teams = _teams(uow).list_for_lab(_lab_id(lab_id))
    return [dto.TeamOutputDTO.from_entity(t) for t in teams]


def get_team(*, uow: unit_of_work.UnitOfWork, team_id: str) -> dto.TeamOutputDTO:
    with uow.transaction():
        team = _teams(uow).get(_team_id(team_id))
    return dto.TeamOutputDTO.from_entity(team)


def find_team_of(
    *, uow: unit_of_work.UnitOfWork, lab_id: str, user_id: str
) -> dto.TeamOutputDTO | None:
    with uow.transaction():
        team = _teams(uow).find_for_member(_lab_id(lab_id), _user(user_id))
    return None if team is None else dto.TeamOutputDTO.from_entity(team)


def create_team(
    *, uow: unit_of_work.UnitOfWork, lab_id: str, user_id: str, name: str
) -> dto.TeamOutputDTO:
    """Crea el equipo con su creador dentro. Ya en otro equipo del lab ⇒ 409."""
    user = _user(user_id)
    with uow.transaction():
        lab = uow.repo(aggregate.Lab).get(_lab_id(lab_id))
        max_size = lab.ensure_team_lab()
        repo = _teams(uow)
        if repo.find_for_member(lab.id, user) is not None:
            raise exceptions.AlreadyInTeamError()
        team = aggregate.Team.create(
            lab_id=lab.id,
            course_id=lab.course_id,
            name=value_objects.TeamName(value=name),
            members=[user],
            max_size=max_size,
        )
        repo.add(team)
    return dto.TeamOutputDTO.from_entity(team)


def create_team_by_teacher(
    *,
    uow: unit_of_work.UnitOfWork,
    lab_id: str,
    name: str,
    member_ids: list[str],
    actor: audit.Actor,
) -> dto.TeamOutputDTO:
    """Equipo del docente (vacío o con integrantes que aún no tienen equipo en el lab).
    Nombre repetido en el lab (sin distinguir mayúsculas) ⇒ 409 `team_name_taken`;
    alguien ya en otro equipo ⇒ 409 `already_in_team` con `details.members`. Que sean
    estudiantes activos lo valida el orquestador."""
    members = [_user(m) for m in dict.fromkeys(member_ids)]
    team_name = value_objects.TeamName(value=name)
    with uow.transaction():
        lab = uow.repo(aggregate.Lab).get(_lab_id(lab_id))
        max_size = lab.ensure_team_lab()
        repo = _teams(uow)
        _ensure_name_free(repo.list_for_lab(lab.id), team_name)
        taken = [str(m) for m in members if repo.find_for_member(lab.id, m) is not None]
        if taken:
            raise exceptions.StudentsAlreadyInTeamError(taken)
        team = aggregate.Team.create(
            lab_id=lab.id,
            course_id=lab.course_id,
            name=team_name,
            members=members,
            max_size=max_size,
        )
        repo.add(team)
        uow.audit.add(_created_entry(team, actor))
    return dto.TeamOutputDTO.from_entity(team)


def create_teams_bulk(
    *,
    uow: unit_of_work.UnitOfWork,
    lab_id: str,
    prefix: str,
    count: int,
    actor: audit.Actor,
) -> list[dto.TeamOutputDTO]:
    """Crea los equipos vacíos «<prefijo> 1»…«<prefijo> N» que falten (los nombres que ya
    existen se saltan). Devuelve sólo los creados."""
    if not 1 <= count <= value_objects.MAX_BULK_TEAMS:
        raise commons_exceptions.ValidationError(
            f"Se pueden crear entre 1 y {value_objects.MAX_BULK_TEAMS} equipos a la vez.",
            code="validation_error",
            details={"fields": {"count": f"Entre 1 y {value_objects.MAX_BULK_TEAMS}."}},
        )
    names = [value_objects.TeamName(value=f"{prefix} {i}") for i in range(1, count + 1)]
    created: list[aggregate.Team] = []
    with uow.transaction():
        lab = uow.repo(aggregate.Lab).get(_lab_id(lab_id))
        max_size = lab.ensure_team_lab()
        repo = _teams(uow)
        existing = {_name_key(t.name) for t in repo.list_for_lab(lab.id)}
        for team_name in names:
            if _name_key(team_name) in existing:
                continue
            team = aggregate.Team.create(
                lab_id=lab.id,
                course_id=lab.course_id,
                name=team_name,
                members=[],
                max_size=max_size,
            )
            repo.add(team)
            uow.audit.add(_created_entry(team, actor))
            existing.add(_name_key(team_name))
            created.append(team)
    return [dto.TeamOutputDTO.from_entity(t) for t in created]


def rename_team(
    *, uow: unit_of_work.UnitOfWork, team_id: str, name: str, actor: audit.Actor
) -> dto.TeamOutputDTO:
    team_name = value_objects.TeamName(value=name)
    with uow.transaction():
        repo = _teams(uow)
        team = repo.get(_team_id(team_id))
        others = [t for t in repo.list_for_lab(team.lab_id) if t.id != team.id]
        _ensure_name_free(others, team_name)
        previous = team.name.value
        if team.rename(team_name):
            repo.update(team)
            uow.audit.add(
                _team_entry(
                    team,
                    value_objects.AuditAction.TEAM_RENAMED,
                    actor,
                    {"from": previous, "name": team.name.value},
                )
            )
    return dto.TeamOutputDTO.from_entity(team)


def delete_team(*, uow: unit_of_work.UnitOfWork, team_id: str, actor: audit.Actor) -> None:
    """Sus integrantes quedan sin equipo. Con entregas ⇒ 409 `team_has_submissions` (lo
    comprueba el orquestador; la FK `RESTRICT` de `submissions.team_id` lo garantiza)."""
    with uow.transaction():
        repo = _teams(uow)
        team = repo.get(_team_id(team_id))
        repo.delete(team.id)
        uow.audit.add(
            _team_entry(
                team,
                value_objects.AuditAction.TEAM_DELETED,
                actor,
                {"name": team.name.value, "members": [str(m) for m in team.members]},
            )
        )


def auto_assign(
    *,
    uow: unit_of_work.UnitOfWork,
    lab_id: str,
    student_ids: list[str],
    actor: audit.Actor,
) -> list[dto.TeamOutputDTO]:
    """Reparte al azar a `student_ids` que aún no tengan equipo entre los equipos NO
    bloqueados con hueco, llenando primero los que tienen menos integrantes. Quien no
    quepa sigue sin equipo. Devuelve todos los equipos del lab."""
    with uow.transaction():
        lab = uow.repo(aggregate.Lab).get(_lab_id(lab_id))
        max_size = lab.ensure_team_lab()
        repo = _teams(uow)
        teams = repo.list_for_lab(lab.id)
        assigned = {m for t in teams for m in t.members}
        pending = [u for u in (_user(s) for s in dict.fromkeys(student_ids)) if u not in assigned]
        _RANDOM.shuffle(pending)
        open_teams = [t for t in teams if not t.locked and t.free_slots(max_size)]
        changed: dict[teaching_value_objects.TeamId, aggregate.Team] = {}
        for student in pending:
            if not open_teams:
                break
            target = min(open_teams, key=lambda t: len(t.members))
            target.add_member_by_teacher(student, max_size=max_size)
            changed[target.id] = target
            if not target.free_slots(max_size):
                open_teams.remove(target)
        for team in changed.values():
            repo.update(team)
            uow.audit.add(
                _team_entry(
                    team,
                    value_objects.AuditAction.TEAM_MEMBERS_SET,
                    actor,
                    {"members": [str(m) for m in team.members], "auto": True},
                )
            )
    return [dto.TeamOutputDTO.from_entity(t) for t in teams]


def join_team(
    *, uow: unit_of_work.UnitOfWork, lab_id: str, user_id: str, code: str
) -> dto.TeamOutputDTO:
    user = _user(user_id)
    join_code = value_objects.TeamJoinCode.parse(code)
    if join_code is None:
        raise exceptions.InvalidTeamCodeError()
    with uow.transaction():
        lab = uow.repo(aggregate.Lab).get(_lab_id(lab_id))
        max_size = lab.ensure_team_lab()
        repo = _teams(uow)
        team = repo.get_by_code(lab.id, join_code)
        current = repo.find_for_member(lab.id, user)
        if current is not None and current.id != team.id:
            raise exceptions.AlreadyInTeamError()
        team.join(user, max_size=max_size)
        repo.update(team)
    return dto.TeamOutputDTO.from_entity(team)


def leave_team(*, uow: unit_of_work.UnitOfWork, team_id: str, user_id: str) -> dto.TeamOutputDTO:
    with uow.transaction():
        repo = _teams(uow)
        team = repo.get(_team_id(team_id))
        team.leave(_user(user_id))
        repo.update(team)
    return dto.TeamOutputDTO.from_entity(team)


def set_team_members(
    *,
    uow: unit_of_work.UnitOfWork,
    team_id: str,
    member_ids: list[str],
    actor: audit.Actor,
) -> dto.TeamOutputDTO:
    """Reasignación del docente: quien esté en otro equipo del lab se mueve a este (aunque
    alguno de los dos esté bloqueado). Validar que son estudiantes activos es del
    orquestador."""
    members = [_user(m) for m in member_ids]
    with uow.transaction():
        repo = _teams(uow)
        team = repo.get(_team_id(team_id))
        lab = uow.repo(aggregate.Lab).get(team.lab_id)
        max_size = lab.ensure_team_lab()
        for member in members:
            other = repo.find_for_member(team.lab_id, member)
            if other is not None and other.id != team.id:
                other.remove_member_by_teacher(member)
                repo.update(other)
        team.set_members(members, max_size=max_size)
        repo.update(team)
        uow.audit.add(
            _team_entry(
                team,
                value_objects.AuditAction.TEAM_MEMBERS_SET,
                actor,
                {"members": [str(m) for m in team.members]},
            )
        )
    return dto.TeamOutputDTO.from_entity(team)


def lock_team(
    *, uow: unit_of_work.UnitOfWork, team_id: str, locked: bool, actor: audit.Actor
) -> dto.TeamOutputDTO:
    with uow.transaction():
        repo = _teams(uow)
        team = repo.get(_team_id(team_id))
        if team.set_locked(locked):
            repo.update(team)
            action = (
                value_objects.AuditAction.TEAM_LOCKED
                if locked
                else value_objects.AuditAction.TEAM_UNLOCKED
            )
            uow.audit.add(_team_entry(team, action, actor))
    return dto.TeamOutputDTO.from_entity(team)


# --------------------------------------------------------------------------------------


def _schedule(opens_at: Any, due_at: Any, policy: str | None) -> value_objects.Schedule:
    try:
        deadline_policy = value_objects.DeadlinePolicy(policy or "")
    except ValueError as exc:
        raise _invalid(
            "deadline_policy", "La política debe ser strict, late_marked o none."
        ) from exc
    return value_objects.Schedule(
        opens_at=_posix(opens_at), due_at=_posix(due_at), deadline_policy=deadline_policy
    )


def _team_setup(team_mode: str | None, max_team_size: int | None) -> value_objects.TeamSetup:
    try:
        mode = value_objects.TeamMode(team_mode or "")
    except ValueError as exc:
        raise _invalid("team_mode", "El modo debe ser individual o team.") from exc
    return value_objects.TeamSetup(team_mode=mode, max_team_size=max_team_size)


def _module(raw: str) -> value_objects.LabModule:
    try:
        return value_objects.LabModule(raw)
    except ValueError as exc:
        raise _invalid("module", f"Módulo desconocido: {raw}.") from exc


def _invalid(field: str, message: str) -> commons_exceptions.ValidationError:
    return commons_exceptions.ValidationError(
        message, code="validation_error", details={"field": field}
    )


def _posix(value: Any) -> base_value_objects.PosixTime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise _invalid("due_at", "Las fechas deben incluir zona horaria (ISO 8601).")
    return base_value_objects.PosixTime.from_datetime(value)


def _dt(value: base_value_objects.PosixTime | None) -> Any:
    return None if value is None else value.to_datetime()


def _lab_id(raw: str) -> teaching_value_objects.LabId:
    try:
        return teaching_value_objects.LabId(value=uuid.UUID(raw))
    except ValueError as exc:
        raise exceptions.LabNotFoundError() from exc


def _team_id(raw: str) -> teaching_value_objects.TeamId:
    try:
        return teaching_value_objects.TeamId(value=uuid.UUID(raw))
    except ValueError as exc:
        raise exceptions.TeamNotFoundError() from exc


def _user(raw: str) -> teaching_value_objects.UserRef:
    parsed = teaching_value_objects.UserRef.parse(raw)
    if parsed is None:
        raise _invalid("members", "Id de usuario no válido.")
    return parsed


def _lab_entry(
    lab: aggregate.Lab,
    action: value_objects.AuditAction,
    actor: audit.Actor,
    changes: dict[str, Any] | None = None,
) -> audit.AuditEntry:
    return audit.AuditEntry(
        actor=actor,
        action=action.value,
        aggregate_type=value_objects.AuditAggregateType.LAB.value,
        aggregate_id=str(lab.id),
        changes={"course_id": str(lab.course_id)} | (changes or {}),
    )


def _name_key(name: value_objects.TeamName) -> str:
    return name.value.casefold()


def _ensure_name_free(teams: list[aggregate.Team], name: value_objects.TeamName) -> None:
    if any(_name_key(t.name) == _name_key(name) for t in teams):
        raise exceptions.TeamNameTakenError(name.value)


def _created_entry(team: aggregate.Team, actor: audit.Actor) -> audit.AuditEntry:
    return _team_entry(
        team,
        value_objects.AuditAction.TEAM_CREATED,
        actor,
        {"name": team.name.value, "members": [str(m) for m in team.members]},
    )


def _team_entry(
    team: aggregate.Team,
    action: value_objects.AuditAction,
    actor: audit.Actor,
    changes: dict[str, Any] | None = None,
) -> audit.AuditEntry:
    return audit.AuditEntry(
        actor=actor,
        action=action.value,
        aggregate_type=value_objects.AuditAggregateType.TEAM.value,
        aggregate_id=str(team.id),
        changes={"lab_id": str(team.lab_id)} | (changes or {}),
    )


def _labs(uow: unit_of_work.UnitOfWork) -> repository.DefaultLabRepository:
    return typing.cast(repository.DefaultLabRepository, uow.repo(aggregate.Lab))


def _teams(uow: unit_of_work.UnitOfWork) -> repository.DefaultTeamRepository:
    return typing.cast(repository.DefaultTeamRepository, uow.repo(aggregate.Team))
