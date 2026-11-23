"""Integración con Postgres real: garantías que da la BD y no sólo el dominio."""

import itertools
import uuid

import pytest
import sqlalchemy as sa

from backend.commons.adapters import unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import exceptions as commons_exceptions
from backend.identity.users.services import dto as users_dto
from backend.identity.users.services import users
from backend.orchestrators import ports
from backend.projects.projects.services import dto as projects_dto
from backend.projects.projects.services import projects
from backend.teaching.commons import value_objects as tvo
from backend.teaching.courses.domain.model import value_objects as courses_vo
from backend.teaching.courses.services import courses
from backend.teaching.courses.services import dto as courses_dto
from backend.teaching.labs.adapters import repository as labs_repository
from backend.teaching.labs.domain.model import aggregate as labs_aggregate
from backend.teaching.labs.domain.model import exceptions as labs_exceptions
from backend.teaching.labs.services import dto as labs_dto
from backend.teaching.labs.services import labs
from backend.teaching.services import dto as teaching_dto
from backend.teaching.services import submissions_orchestrator
from backend.teaching.submissions.adapters import repository as subs_repository
from backend.teaching.submissions.domain.model import aggregate as subs_aggregate
from backend.teaching.submissions.domain.model import value_objects as subs_vo
from tests.unit.backend.identity import builders
from tests.unit.backend.projects.projects import test_projects as unit_projects

pytestmark = pytest.mark.integration

_ACTOR = audit.Actor(id=None, label="test")


def _user(uow: unit_of_work.UnitOfWork, email: str) -> tvo.Viewer:
    users.register(
        uow=uow,
        input_dto=users_dto.RegisterInputDTO(
            email=email,
            full_name=email.split("@")[0],
            password="caballo-bateria-grapa",
            accept_data_policy=True,
        ),
        config=builders.CONFIG,
        context=users_dto.RequestContext(ip=f"10.0.{uuid.uuid4().int % 250}.1"),
    )
    with uow.transaction():
        uid = uow.session.execute(
            sa.text("SELECT id FROM users WHERE email = :e"), {"e": email}
        ).scalar_one()
    return tvo.Viewer(user_id=tvo.UserRef(value=uid))


def _course_with_students(
    uow: unit_of_work.UnitOfWork, n: int
) -> tuple[tvo.Viewer, str, list[tvo.Viewer]]:
    teacher = _user(uow, f"t{uuid.uuid4().hex[:6]}@example.com")
    course = courses.create_course(
        uow=uow,
        viewer=teacher,
        actor=_ACTOR,
        input_dto=courses_dto.CreateCourseInputDTO(name="Curso", period="2027-I"),
    )
    assert course.join_code is not None
    students = []
    for _ in range(n):
        student = _user(uow, f"s{uuid.uuid4().hex[:6]}@example.com")
        courses.join(uow=uow, viewer=student, actor=_ACTOR, code=course.join_code)
        courses.decide_membership(
            uow=uow,
            viewer=teacher,
            actor=_ACTOR,
            course_id=course.id,
            user_id=str(student.user_id),
            decision=courses_vo.MembershipDecision.APPROVE,
        )
        students.append(student)
    return teacher, course.id, students


def _lab(uow: unit_of_work.UnitOfWork, course_id: str, teacher: tvo.Viewer, **extra: object) -> str:
    body = {
        "title": "Lab",
        "deadline_policy": "none",
        "team_mode": "individual",
        "grade_scale": {"type": "numeric", "min": 0, "max": 5},
        "allow_resubmission": False,
    } | extra
    lab = labs.create_lab(
        uow=uow,
        course_id=course_id,
        created_by=str(teacher.user_id),
        actor=_ACTOR,
        input_dto=labs_dto.LabInputDTO.model_validate(body),
    )
    labs.publish_lab(uow=uow, lab_id=lab.id, actor=_ACTOR)
    return lab.id


def test_one_team_per_lab_is_enforced_by_postgres(db: sa.Engine) -> None:
    uow = unit_of_work.build()
    teacher, course_id, (a, b) = _course_with_students(uow, 2)
    lab_id = _lab(uow, course_id, teacher, team_mode="team", max_team_size=3)
    team_a = labs.create_team(uow=uow, lab_id=lab_id, user_id=str(a.user_id), name="A")
    team_b = labs.create_team(uow=uow, lab_id=lab_id, user_id=str(b.user_id), name="B")
    # Saltándose la comprobación del servicio (como haría una carrera): la BD lo impide.
    with pytest.raises(labs_exceptions.AlreadyInTeamError), uow.transaction():
        repo = labs_repository.DefaultTeamRepository(uow.session)
        loaded = repo.get(tvo.TeamId(value=uuid.UUID(team_b.id)))
        loaded.members = [*loaded.members, a.user_id]
        loaded.touch()
        repo.update(loaded)
    assert [m.user_id for m in labs.get_team(uow=uow, team_id=team_a.id).members] == [
        str(a.user_id)
    ]


def test_stale_team_version_loses_the_last_slot(db: sa.Engine) -> None:
    uow = unit_of_work.build()
    teacher, course_id, (a, b, c) = _course_with_students(uow, 3)
    lab_id = _lab(uow, course_id, teacher, team_mode="team", max_team_size=2)
    team = labs.create_team(uow=uow, lab_id=lab_id, user_id=str(a.user_id), name="A")
    with uow.transaction():
        stale: labs_aggregate.Team = labs_repository.DefaultTeamRepository(uow.session).get(
            tvo.TeamId(value=uuid.UUID(team.id))
        )
    labs.join_team(uow=uow, lab_id=lab_id, user_id=str(b.user_id), code=team.join_code or "")
    stale.join(c.user_id, max_size=2)  # creía que quedaba hueco
    with pytest.raises(commons_exceptions.ConcurrentModificationError), uow.transaction():
        labs_repository.DefaultTeamRepository(uow.session).update(stale)


def _submission(
    lab_id: str,
    course_id: str,
    who: tvo.UserRef,
    version_id: uuid.UUID,
    project_id: uuid.UUID,
    team_id: tvo.TeamId | None = None,
) -> subs_aggregate.Submission:
    return subs_aggregate.Submission.submit(
        lab_id=tvo.LabId(value=uuid.UUID(lab_id)),
        course_id=tvo.CourseId(value=uuid.UUID(course_id)),
        submitter_id=who,
        team_id=team_id,
        member_ids=[who],
        previous=None,
        allow_resubmission=False,
        project=subs_vo.FrozenProject(
            project_id=project_id, project_name="p", version_id=version_id, version_n=1
        ),
        files=[],
        is_late=False,
    )


def test_attempt_is_unique_and_frozen_version_cannot_be_deleted(db: sa.Engine) -> None:
    uow = unit_of_work.build()
    teacher, course_id, (a,) = _course_with_students(uow, 1)
    lab_id = _lab(uow, course_id, teacher)
    project = projects.create_project(
        uow=uow,
        owner_id=str(a.user_id),
        input_dto=projects_dto.CreateProjectInputDTO(
            name="P", module="fpga", content=unit_projects.content("x")
        ),
    )
    frozen = projects.freeze_version(
        uow=uow, owner_id=str(a.user_id), project_id=project.id, version_id=None
    )
    vid, pid = uuid.UUID(frozen.version_id), uuid.UUID(project.id)
    with uow.transaction():
        subs_repository.DefaultSubmissionRepository(uow.session).add(
            _submission(lab_id, course_id, a.user_id, vid, pid)
        )
    # Dos entregas "a la vez" que creen ser el intento 1.
    with pytest.raises(commons_exceptions.ConcurrentModificationError), uow.transaction():
        subs_repository.DefaultSubmissionRepository(uow.session).add(
            _submission(lab_id, course_id, a.user_id, vid, pid)
        )
    with pytest.raises(sa.exc.IntegrityError), db.begin() as conn:
        conn.execute(sa.text("DELETE FROM project_versions WHERE id = :v"), {"v": vid})


def test_team_with_submissions_cannot_be_deleted_even_skipping_the_check(db: sa.Engine) -> None:
    uow = unit_of_work.build()
    teacher, course_id, (a,) = _course_with_students(uow, 1)
    lab_id = _lab(uow, course_id, teacher, team_mode="team", max_team_size=2)
    team = labs.create_team_by_teacher(
        uow=uow, lab_id=lab_id, name="Pareja 1", member_ids=[str(a.user_id)], actor=_ACTOR
    )
    project = projects.create_project(
        uow=uow,
        owner_id=str(a.user_id),
        input_dto=projects_dto.CreateProjectInputDTO(
            name="P", module="fpga", content=unit_projects.content("x")
        ),
    )
    frozen = projects.freeze_version(
        uow=uow, owner_id=str(a.user_id), project_id=project.id, version_id=None
    )
    team_id = tvo.TeamId(value=uuid.UUID(team.id))
    with uow.transaction():
        subs_repository.DefaultSubmissionRepository(uow.session).add(
            _submission(
                lab_id,
                course_id,
                a.user_id,
                uuid.UUID(frozen.version_id),
                uuid.UUID(project.id),
                team_id=team_id,
            )
        )
    # Sin pasar por el orquestador (como una entrega que llega a la vez): la FK lo impide.
    with pytest.raises(labs_exceptions.TeamHasSubmissionsError):
        labs.delete_team(uow=uow, team_id=team.id, actor=_ACTOR)
    assert labs.get_team(uow=uow, team_id=team.id).member_ids() == [str(a.user_id)]


def test_join_code_collision_is_retried(db: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    uow = unit_of_work.build()
    teacher = _user(uow, "docente@example.com")
    original_new = courses_vo.JoinCode.new
    codes = itertools.chain(["AAAABBBB", "AAAABBBB"], iter(lambda: original_new().value, None))
    monkeypatch.setattr(courses_vo.JoinCode, "new", classmethod(lambda cls: cls(value=next(codes))))
    first = courses.create_course(
        uow=uow,
        viewer=teacher,
        actor=_ACTOR,
        input_dto=courses_dto.CreateCourseInputDTO(name="A", period="x"),
    )
    second = courses.create_course(
        uow=uow,
        viewer=teacher,
        actor=_ACTOR,
        input_dto=courses_dto.CreateCourseInputDTO(name="B", period="x"),
    )
    monkeypatch.setattr(courses_vo.JoinCode, "new", original_new)
    assert first.join_code == "AAAA-BBBB" and second.join_code not in (None, "AAAA-BBBB")


def test_submit_orchestrator_with_real_ports_and_file_access(db: sa.Engine) -> None:
    """El orquestador con los adaptadores reales: congela, crea y autoriza el archivo."""
    uow = unit_of_work.build()
    teacher, course_id, (a, b) = _course_with_students(uow, 2)
    lab_id = _lab(uow, course_id, teacher)
    project = projects.create_project(
        uow=uow,
        owner_id=str(a.user_id),
        input_dto=projects_dto.CreateProjectInputDTO(
            name="P", module="fpga", content=unit_projects.content("entregado")
        ),
    )
    created = submissions_orchestrator.submit(
        uow=uow,
        viewer=a,
        actor=_ACTOR,
        projects_port=ports.ProjectsAdapter(),
        files_port=ports.FilesAdapter(),
        directory=ports.IdentityUserDirectory(),
        lab_id=lab_id,
        input_dto=teaching_dto.SubmitInputDTO(project_id=project.id),
    )
    assert created.content["files"][0]["text"] == "entregado"  # type: ignore[index]
    projects.autosave(
        uow=uow,
        owner_id=str(a.user_id),
        project_id=project.id,
        input_dto=projects_dto.AutosaveInputDTO(
            content=unit_projects.content("después"), base_version=1
        ),
    )
    again = submissions_orchestrator.get_submission(
        uow=uow,
        viewer=teacher,
        projects_port=ports.ProjectsAdapter(),
        files_port=ports.FilesAdapter(),
        directory=ports.IdentityUserDirectory(),
        submission_id=created.id,
    )
    assert again.content["files"][0]["text"] == "entregado"  # type: ignore[index]
    with db.connect() as conn:
        actions = conn.execute(sa.text("SELECT action FROM audit_log")).scalars().all()
    assert {"course_created", "membership_approved", "lab_published", "submitted"} <= set(actions)
    policy = ports.TeachingBlobAccessPolicy()
    assert (
        policy.can_view(user_id=str(b.user_id), is_admin=False, blob_id=str(uuid.uuid4())) is False
    )
