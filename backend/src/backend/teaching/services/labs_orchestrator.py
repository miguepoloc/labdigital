"""Labs (LD-5): permisos del curso (`courses`) + `labs` + la última entrega del que mira
(`submissions`, para `my_submission`). Sólo los publicados son visibles al estudiante."""

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.labs.services import dto as labs_dto
from backend.teaching.labs.services import labs
from backend.teaching.services import _access, dto
from backend.teaching.submissions.services import dto as submissions_dto
from backend.teaching.submissions.services import submissions


def _view(
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    lab: labs_dto.LabOutputDTO,
    *,
    is_student: bool,
) -> dto.LabViewOutputDTO:
    mine = None
    if is_student:
        team_id = None
        if lab.team_mode == "team":
            team = labs.find_team_of(uow=uow, lab_id=lab.id, user_id=str(viewer.user_id))
            team_id = team.id if team else None
        if lab.team_mode != "team" or team_id is not None:
            latest = submissions.latest_for_owner(
                uow=uow,
                lab_id=lab.id,
                student_id=None if team_id else str(viewer.user_id),
                team_id=team_id,
            )
            mine = (
                None if latest is None else submissions_dto.SubmissionSummaryDTO.from_record(latest)
            )
    return dto.LabViewOutputDTO(**lab.model_dump(), my_submission=mine)


def create_lab(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    course_id: str,
    input_dto: labs_dto.LabInputDTO,
) -> dto.LabViewOutputDTO:
    access = _access.course(uow, viewer, course_id)
    _access.require_manage(access)
    _access.require_open(access)
    created = labs.create_lab(
        uow=uow,
        course_id=access.course_id,
        created_by=str(viewer.user_id),
        actor=actor,
        input_dto=input_dto,
    )
    return _view(uow, viewer, created, is_student=False)


def list_labs(
    *, uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, course_id: str
) -> list[dto.LabViewOutputDTO]:
    access = _access.course(uow, viewer, course_id)
    if not access.can_manage:
        _access.require_active_student(access)
    found = labs.list_labs(
        uow=uow, course_id=access.course_id, published_only=not access.can_manage
    )
    is_student = access.is_active_student and not access.can_manage
    return [_view(uow, viewer, lab, is_student=is_student) for lab in found]


def get_lab(
    *, uow: unit_of_work.UnitOfWork, viewer: teaching_value_objects.Viewer, lab_id: str
) -> dto.LabViewOutputDTO:
    lab, access = _access.lab(uow, viewer, lab_id)
    if not access.can_manage:
        _access.require_active_student(access)
    return _view(uow, viewer, lab, is_student=not access.can_manage)


def update_lab(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    lab_id: str,
    input_dto: labs_dto.LabInputDTO,
) -> dto.LabViewOutputDTO:
    _, access = _access.lab(uow, viewer, lab_id)
    _access.require_manage(access)
    _access.require_open(access)
    updated = labs.update_lab(uow=uow, lab_id=lab_id, actor=actor, input_dto=input_dto)
    return _view(uow, viewer, updated, is_student=False)


def publish_lab(
    *,
    uow: unit_of_work.UnitOfWork,
    viewer: teaching_value_objects.Viewer,
    actor: audit.Actor,
    lab_id: str,
) -> dto.LabViewOutputDTO:
    _, access = _access.lab(uow, viewer, lab_id)
    _access.require_manage(access)
    _access.require_open(access)
    published = labs.publish_lab(uow=uow, lab_id=lab_id, actor=actor)
    return _view(uow, viewer, published, is_student=False)
