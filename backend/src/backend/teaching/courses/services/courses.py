"""Capa de aplicación de `teaching.courses` (LD-4). Autorización aquí: cada caso de uso
recibe el `Viewer` del access verificado.

- Ver un curso: docente, admin, o estudiante con membresía pendiente/activa. Sin relación
  (o rechazado/retirado) ⇒ 404 (no se revela que existe).
- Gestionarlo (editar, archivar, rotar código, ver y decidir membresías): docente o admin;
  un estudiante del curso ⇒ 403 `forbidden`.
"""

import typing
import uuid

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import exceptions as commons_exceptions
from backend.teaching.commons import dto as teaching_dto
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.adapters import repository
from backend.teaching.courses.domain.model import aggregate, exceptions, value_objects
from backend.teaching.courses.services import dto

_VISIBLE_STATUSES = (value_objects.MembershipStatus.PENDING, value_objects.MembershipStatus.ACTIVE)


def create_course(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    input_dto: dto.CreateCourseInputDTO,
) -> dto.CourseOutputDTO:
    course = aggregate.Course.create(
        owner_id=viewer.user_id,
        name=value_objects.CourseName(value=input_dto.name),
        period=value_objects.Period(value=input_dto.period),
        description=value_objects.Description(value=input_dto.description),
    )
    teacher = aggregate.Membership.for_teacher(course_id=course.id, user_id=viewer.user_id)
    with uow.transaction():
        uow.repo(aggregate.Course).add(course)
        uow.repo(aggregate.Membership).add(teacher)
        uow.audit.add(_course_entry(course, value_objects.AuditAction.COURSE_CREATED, actor))
    return dto.CourseOutputDTO.from_entity(course, teacher)


def list_my_courses(
    *, uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer
) -> list[dto.CourseOutputDTO]:
    """Los míos como docente y como estudiante (cualquier estado), con mi rol y estado."""
    with uow.transaction():
        memberships = {m.course_id: m for m in _memberships(uow).list_for_user(viewer.user_id)}
        courses = _courses(uow).list_by_ids(list(memberships))
        return [_view(uow, c, memberships[c.id], viewer) for c in courses]


def get_course(
    *, uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, course_id: str
) -> dto.CourseOutputDTO:
    with uow.transaction():
        course, membership = _load_visible(uow, viewer, course_id)
        return _view(uow, course, membership, viewer)


def get_access(
    *, uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, course_id: str
) -> teaching_dto.CourseAccessDTO:
    """Para los orquestadores de labs/equipos/entregas. 404 si no hay relación visible."""
    with uow.transaction():
        course, membership = _load_visible(uow, viewer, course_id)
    return teaching_dto.CourseAccessDTO(
        course_id=str(course.id),
        owner_id=str(course.owner_id),
        can_manage=_can_manage(course, viewer),
        is_active_student=membership is not None and membership.is_active_student,
        archived=course.is_archived,
    )


def update_course(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    course_id: str,
    input_dto: dto.UpdateCourseInputDTO,
) -> dto.CourseOutputDTO:
    """`archived: true|false` archiva/desarchiva; el resto de campos no se edita si el curso
    queda archivado (`course_archived`)."""
    with uow.transaction():
        course, membership = _load_managed(uow, viewer, course_id)
        if input_dto.archived is False and course.unarchive():
            uow.audit.add(_course_entry(course, value_objects.AuditAction.COURSE_UNARCHIVED, actor))
        changes = course.update(
            name=value_objects.CourseName(value=input_dto.name)
            if input_dto.name is not None
            else None,
            period=value_objects.Period(value=input_dto.period)
            if input_dto.period is not None
            else None,
            description=value_objects.Description(value=input_dto.description)
            if input_dto.description is not None
            else None,
        )
        if changes:
            uow.audit.add(
                _course_entry(course, value_objects.AuditAction.COURSE_UPDATED, actor, changes)
            )
        if input_dto.archived and course.archive():
            uow.audit.add(_course_entry(course, value_objects.AuditAction.COURSE_ARCHIVED, actor))
        uow.repo(aggregate.Course).update(course)
        return _view(uow, course, membership, viewer)


def rotate_join_code(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    course_id: str,
) -> dto.CourseOutputDTO:
    """El código anterior deja de servir al instante; las solicitudes ya hechas siguen."""
    with uow.transaction():
        course, membership = _load_managed(uow, viewer, course_id)
        course.rotate_join_code()
        uow.repo(aggregate.Course).update(course)
        uow.audit.add(_course_entry(course, value_objects.AuditAction.JOIN_CODE_ROTATED, actor))
        return _view(uow, course, membership, viewer)


def join(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    code: str,
) -> dto.CourseOutputDTO:
    """Solicitud de inscripción (queda `pending` hasta que el docente apruebe) y devuelve
    `Course`. Pendiente ⇒ idempotente; rechazada/retirada ⇒ vuelve a `pending`; ya activa o
    docente ⇒ 409 `already_member`. Código inexistente o curso archivado ⇒ 404
    `invalid_code`."""
    join_code = value_objects.JoinCode.parse(code)
    if join_code is None:
        raise exceptions.InvalidJoinCodeError()
    with uow.transaction():
        course = _courses(uow).get_by_join_code(join_code)
        if course.is_archived:
            raise exceptions.InvalidJoinCodeError()
        repo = _memberships(uow)
        membership = repo.find(course.id, viewer.user_id)
        if membership is None:
            membership = aggregate.Membership.request(course_id=course.id, user_id=viewer.user_id)
            repo.add(membership)
            uow.audit.add(
                _membership_entry(membership, value_objects.AuditAction.JOIN_REQUESTED, actor)
            )
        elif membership.is_teacher or membership.is_active_student:
            raise exceptions.AlreadyMemberError()
        elif membership.rerequest():
            repo.update(membership)
            uow.audit.add(
                _membership_entry(membership, value_objects.AuditAction.JOIN_REQUESTED, actor)
            )
        return _view(uow, course, membership, viewer)


def list_members(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    course_id: str,
    status: str | None,
) -> list[dto.MembershipOutputDTO]:
    status_vo = _status(status) if status else None
    with uow.transaction():
        course, _ = _load_managed(uow, viewer, course_id)
        members = _memberships(uow).list_for_course(course.id, status=status_vo)
    return [dto.MembershipOutputDTO.from_entity(m) for m in members]


def decide_membership(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    course_id: str,
    user_id: str,
    decision: value_objects.MembershipDecision,
) -> dto.MembershipOutputDTO:
    """Aprobar, rechazar o retirar a un estudiante (docente/admin). Auditado."""
    target = teaching_value_objects.UserRef.parse(user_id)
    if target is None:
        raise exceptions.MembershipNotFoundError()
    actions = {
        value_objects.MembershipDecision.APPROVE: value_objects.AuditAction.MEMBERSHIP_APPROVED,
        value_objects.MembershipDecision.REJECT: value_objects.AuditAction.MEMBERSHIP_REJECTED,
        value_objects.MembershipDecision.REMOVE: value_objects.AuditAction.MEMBERSHIP_REMOVED,
    }
    with uow.transaction():
        course, _ = _load_managed(uow, viewer, course_id)
        if decision is value_objects.MembershipDecision.APPROVE:
            course.ensure_open()
        repo = _memberships(uow)
        membership = repo.find(course.id, target)
        if membership is None:
            raise exceptions.MembershipNotFoundError()
        old_status = membership.status
        if membership.decide(decision):
            repo.update(membership)
            uow.audit.add(
                _membership_entry(
                    membership,
                    actions[decision],
                    actor,
                    {"status": {"old": old_status.value, "new": membership.status.value}},
                )
            )
    return dto.MembershipOutputDTO.from_entity(membership)


def list_active_student_ids(*, uow: unit_of_work.UnitOfWork, course_id: str) -> list[str]:
    """Sin autorización: sólo para orquestadores que ya la comprobaron (notas, equipos)."""
    with uow.transaction():
        members = _memberships(uow).list_for_course(
            _course_id(course_id),
            status=value_objects.MembershipStatus.ACTIVE,
            role=value_objects.MembershipRole.ESTUDIANTE,
        )
    return [str(m.user_id) for m in members]


# --------------------------------------------------------------------------------------


def _view(
    uow: unit_of_work.UnitOfWork,
    course: aggregate.Course,
    membership: aggregate.Membership | None,
    viewer: teaching_value_objects.Viewer,
) -> dto.CourseOutputDTO:
    """Los conteos de estudiantes/pendientes sólo para quien gestiona el curso."""
    counts = None
    if _can_manage(course, viewer):
        repo = _memberships(uow)
        counts = dto.CourseCountsDTO(
            students=repo.count(course.id, value_objects.MembershipStatus.ACTIVE),
            pending=repo.count(course.id, value_objects.MembershipStatus.PENDING),
        )
    return dto.CourseOutputDTO.from_entity(course, membership, counts=counts)


def _can_manage(course: aggregate.Course, viewer: teaching_value_objects.Viewer) -> bool:
    return viewer.is_admin or course.is_teacher(viewer.user_id)


def _load_visible(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, course_id: str
) -> tuple[aggregate.Course, aggregate.Membership | None]:
    course = _courses(uow).get(_course_id(course_id))
    membership = _memberships(uow).find(course.id, viewer.user_id)
    if _can_manage(course, viewer):
        return course, membership
    if membership is None or membership.status not in _VISIBLE_STATUSES:
        raise exceptions.CourseNotFoundError()
    return course, membership


def _load_managed(
    uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, course_id: str
) -> tuple[aggregate.Course, aggregate.Membership | None]:
    course, membership = _load_visible(uow, viewer, course_id)
    if not _can_manage(course, viewer):
        raise exceptions.NotCourseTeacherError()
    return course, membership


def _course_id(raw: str) -> teaching_value_objects.CourseId:
    try:
        return teaching_value_objects.CourseId(value=uuid.UUID(raw))
    except ValueError as exc:
        raise exceptions.CourseNotFoundError() from exc


def _status(raw: str) -> value_objects.MembershipStatus:
    try:
        return value_objects.MembershipStatus(raw)
    except ValueError as exc:
        raise commons_exceptions.ValidationError(
            "Estado no válido (pending, active, rejected o removed).",
            code="validation_error",
            details={"field": "status"},
        ) from exc


def _course_entry(
    course: aggregate.Course,
    action: value_objects.AuditAction,
    actor: audit.Actor,
    changes: dict[str, typing.Any] | None = None,
) -> audit.AuditEntry:
    return audit.AuditEntry(
        actor=actor,
        action=action.value,
        aggregate_type=value_objects.AuditAggregateType.COURSE.value,
        aggregate_id=str(course.id),
        changes=changes or {},
    )


def _membership_entry(
    membership: aggregate.Membership,
    action: value_objects.AuditAction,
    actor: audit.Actor,
    changes: dict[str, typing.Any] | None = None,
) -> audit.AuditEntry:
    return audit.AuditEntry(
        actor=actor,
        action=action.value,
        aggregate_type=value_objects.AuditAggregateType.MEMBERSHIP.value,
        aggregate_id=str(membership.id),
        changes={"course_id": str(membership.course_id), "user_id": str(membership.user_id)}
        | (changes or {}),
    )


def _courses(uow: unit_of_work.UnitOfWork) -> repository.DefaultCourseRepository:
    return typing.cast(repository.DefaultCourseRepository, uow.repo(aggregate.Course))


def _memberships(uow: unit_of_work.UnitOfWork) -> repository.DefaultMembershipRepository:
    return typing.cast(repository.DefaultMembershipRepository, uow.repo(aggregate.Membership))
