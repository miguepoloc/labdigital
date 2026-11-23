import datetime
import decimal
import uuid

import pytest
import time_machine

from backend.commons.domain import exceptions as commons_exceptions
from backend.commons.domain import value_objects as base_vo
from backend.teaching.commons import value_objects as tvo
from backend.teaching.courses.domain.model import aggregate as courses
from backend.teaching.courses.domain.model import exceptions as courses_exc
from backend.teaching.courses.domain.model import value_objects as courses_vo
from backend.teaching.labs.domain.model import aggregate as labs
from backend.teaching.labs.domain.model import exceptions as labs_exc
from backend.teaching.labs.domain.model import value_objects as labs_vo
from backend.teaching.services import grades_orchestrator
from backend.teaching.submissions.domain.model import aggregate as subs
from backend.teaching.submissions.domain.model import exceptions as subs_exc
from backend.teaching.submissions.domain.model import value_objects as subs_vo

pytestmark = pytest.mark.unit

ME = tvo.UserRef(value=uuid.uuid4())
OTHER = tvo.UserRef(value=uuid.uuid4())
NOW = datetime.datetime(2030, 3, 1, 12, tzinfo=datetime.UTC)


def _fields(exc: pytest.ExceptionInfo[commons_exceptions.DomainError]) -> set[str]:
    return set(exc.value.details["fields"])


# -- Escala de notas ---------------------------------------------------------------


def test_grade_scale_numeric_validation() -> None:
    scale = tvo.GradeScale.parse({"type": "numeric", "min": 0, "max": 5, "decimals": 1})
    assert scale.validate_grade(4.5).as_json() == 4.5
    assert scale.validate_grade("3").numeric == decimal.Decimal("3.0")
    for bad in (5.1, -0.1, 4.25, None, "abc", True):
        with pytest.raises(commons_exceptions.ValidationError) as info:
            scale.validate_grade(bad)
        assert _fields(info) == {"grade"} and info.value.details["max"] == 5.0
    with pytest.raises(commons_exceptions.ValidationError) as info:
        tvo.GradeScale.parse({"type": "numeric", "min": 3, "max": 1, "decimals": 4})
    assert _fields(info) == {"grade_scale.max", "grade_scale.decimals"}
    with pytest.raises(commons_exceptions.ValidationError) as info:
        tvo.GradeScale.parse(
            {"type": "numeric", "min": 0, "max": 5, "decimals": 0, "pass_mark": 2.5}
        )
    assert _fields(info) == {"grade_scale.pass_mark"}
    with pytest.raises(commons_exceptions.ValidationError) as info:
        tvo.GradeScale.parse({"type": "letras"})
    assert _fields(info) == {"grade_scale.type"}
    assert tvo.GradeScale.from_storage(scale.to_storage()) == scale


def test_grade_scale_pass_fail_is_one_or_zero() -> None:
    scale = tvo.GradeScale.parse({"type": "pass_fail"})
    assert scale.validate_grade(1).as_json() == 1
    assert scale.validate_grade(False).as_json() == 0
    assert scale.validate_grade("pass").passed is True
    with pytest.raises(commons_exceptions.ValidationError):
        scale.validate_grade(0.5)
    with pytest.raises(commons_exceptions.ValidationError):
        tvo.GradeScale.parse({"type": "pass_fail", "decimals": 1})


# -- Códigos ---------------------------------------------------------------------


def test_join_codes_are_unambiguous_and_normalized() -> None:
    for _ in range(200):
        code = courses_vo.JoinCode.new()
        assert len(code.value) == 8 and not set(code.value) & set("01OIL")
    parsed = courses_vo.JoinCode.parse(" abcd-efgh ")
    assert parsed is not None and parsed.value == "ABCDEFGH" and parsed.display == "ABCD-EFGH"
    assert courses_vo.JoinCode.parse("ABCD-EFG0") is None  # 0 no está en el alfabeto
    assert labs_vo.TeamJoinCode.parse("abc234") is not None
    assert labs_vo.TeamJoinCode.parse("abc23") is None


# -- Membresías -------------------------------------------------------------------


def test_membership_transitions() -> None:
    cid = tvo.CourseId.new()
    m = courses.Membership.request(course_id=cid, user_id=ME)
    assert m.status is courses_vo.MembershipStatus.PENDING
    assert m.decide(courses_vo.MembershipDecision.APPROVE) and m.is_active_student
    assert not m.decide(courses_vo.MembershipDecision.APPROVE)  # idempotente
    with pytest.raises(courses_exc.InvalidMembershipTransitionError):
        m.decide(courses_vo.MembershipDecision.REJECT)
    assert m.decide(courses_vo.MembershipDecision.REMOVE)
    assert m.rerequest() and m.status is courses_vo.MembershipStatus.PENDING
    teacher = courses.Membership.for_teacher(course_id=cid, user_id=OTHER)
    with pytest.raises(courses_exc.InvalidMembershipTransitionError):
        teacher.decide(courses_vo.MembershipDecision.REMOVE)


def test_archived_course_rejects_edits_and_rotation() -> None:
    course = courses.Course.create(
        owner_id=ME,
        name=courses_vo.CourseName(value="  Diseño   digital "),
        period=courses_vo.Period(value="2027-I"),
        description=courses_vo.Description(value=""),
    )
    assert course.name.value == "Diseño digital"
    assert course.archive() and not course.archive()
    with pytest.raises(courses_exc.CourseArchivedError):
        course.rotate_join_code()
    with pytest.raises(courses_exc.CourseArchivedError):
        course.update(name=courses_vo.CourseName(value="Otro"), period=None, description=None)


# -- Labs y plazos ----------------------------------------------------------------


def _lab(
    policy: str, *, due: datetime.datetime | None, opens: datetime.datetime | None = None
) -> labs.Lab:
    return labs.Lab.create(
        course_id=tvo.CourseId.new(),
        created_by=ME,
        title=labs_vo.LabTitle(value="Lab"),
        statement_md=labs_vo.StatementMd(value="<b>tal cual</b>"),
        module=labs_vo.LabModule.FPGA,
        schedule=labs_vo.Schedule(
            opens_at=None if opens is None else base_vo.PosixTime.from_datetime(opens),
            due_at=None if due is None else base_vo.PosixTime.from_datetime(due),
            deadline_policy=labs_vo.DeadlinePolicy(policy),
        ),
        team_setup=labs_vo.TeamSetup(team_mode=labs_vo.TeamMode.INDIVIDUAL),
        grade_scale=tvo.GradeScale.parse({"type": "pass_fail"}),
        allow_resubmission=False,
    )


def test_deadline_policies() -> None:
    now = base_vo.PosixTime.from_datetime(NOW)
    past, future = NOW - datetime.timedelta(hours=1), NOW + datetime.timedelta(hours=1)
    assert _lab("late_marked", due=past).evaluate_submission(now=now, returned=False) is True
    assert _lab("late_marked", due=future).evaluate_submission(now=now, returned=False) is False
    assert _lab("none", due=None).evaluate_submission(now=now, returned=False) is False
    with pytest.raises(labs_exc.DeadlinePassedError):
        _lab("strict", due=past).evaluate_submission(now=now, returned=False)
    assert _lab("strict", due=past).evaluate_submission(now=now, returned=True) is True
    with pytest.raises(labs_exc.LabNotOpenError):
        _lab("none", due=None, opens=future).evaluate_submission(now=now, returned=False)
    with pytest.raises(commons_exceptions.ValidationError):
        _lab("strict", due=None)


def test_published_lab_freezes_team_setup_and_scale() -> None:
    lab = _lab("none", due=None)
    lab.publish()
    lab.apply_changes({"title": labs_vo.LabTitle(value="Nuevo")})
    with pytest.raises(labs_exc.LabPublishedError):
        lab.apply_changes(
            {"grade_scale": tvo.GradeScale.parse({"type": "numeric", "min": 0, "max": 5})}
        )


def test_team_size_lock_and_membership() -> None:
    team = labs.Team.create(
        lab_id=tvo.LabId.new(),
        course_id=tvo.CourseId.new(),
        name=labs_vo.TeamName(value="LED"),
        members=[ME],
        max_size=2,
    )
    team.join(OTHER, max_size=2)
    with pytest.raises(labs_exc.TeamFullError):
        team.join(tvo.UserRef(value=uuid.uuid4()), max_size=2)
    team.set_locked(True)
    with pytest.raises(labs_exc.TeamLockedError):
        team.leave(OTHER)
    team.set_members([ME], max_size=2)  # el docente puede aunque esté bloqueado
    assert team.members == [ME]
    with pytest.raises(labs_exc.TeamTooLargeError):
        team.set_members([ME, OTHER, tvo.UserRef(value=uuid.uuid4())], max_size=2)


def _teacher_team(members: list[tvo.UserRef], max_size: int = 2) -> labs.Team:
    return labs.Team.create(
        lab_id=tvo.LabId.new(),
        course_id=tvo.CourseId.new(),
        name=labs_vo.TeamName(value="Pareja 1"),
        members=members,
        max_size=max_size,
    )


def test_teacher_team_creation_respects_max_size_and_dedups() -> None:
    empty = _teacher_team([])
    assert empty.members == []
    assert empty.free_slots(2) == 2
    pair = _teacher_team([ME, OTHER, ME])
    assert pair.members == [ME, OTHER]
    assert pair.free_slots(2) == 0
    with pytest.raises(labs_exc.TeamTooLargeError):
        _teacher_team([ME, OTHER, tvo.UserRef(value=uuid.uuid4())])


def test_teacher_rename_and_add_member_ignore_lock() -> None:
    team = _teacher_team([ME])
    team.set_locked(True)
    assert team.rename(labs_vo.TeamName(value="  Pareja   7 ")) is True
    assert team.name.value == "Pareja 7"
    assert team.rename(labs_vo.TeamName(value="Pareja 7")) is False
    team.add_member_by_teacher(OTHER, max_size=2)
    team.add_member_by_teacher(OTHER, max_size=2)  # idempotente
    assert team.members == [ME, OTHER]
    with pytest.raises(labs_exc.TeamFullError):
        team.add_member_by_teacher(tvo.UserRef(value=uuid.uuid4()), max_size=2)


def test_team_conflict_codes() -> None:
    assert labs_exc.TeamHasSubmissionsError().code == "team_has_submissions"
    assert labs_exc.TeamNameTakenError("Pareja 1").code == "team_name_taken"
    taken = labs_exc.StudentsAlreadyInTeamError(["u1"])
    assert taken.code == "already_in_team"
    assert taken.details == {"members": ["u1"]}


# -- Entregas ---------------------------------------------------------------------


def _submit(previous: subs.Submission | None, *, allow: bool, size: int = 10) -> subs.Submission:
    return subs.Submission.submit(
        lab_id=tvo.LabId.new(),
        course_id=tvo.CourseId.new(),
        submitter_id=ME,
        team_id=None,
        member_ids=[ME],
        previous=previous,
        allow_resubmission=allow,
        project=subs_vo.FrozenProject(
            project_id=uuid.uuid4(), project_name="p", version_id=uuid.uuid4(), version_n=1
        ),
        files=[
            subs_vo.SubmissionFile(
                blob_id=uuid.uuid4(), kind=subs_vo.FileKind.REPORT, size=size, name="a.pdf"
            )
        ],
        is_late=False,
    )


def test_resubmission_rules_and_review_statuses() -> None:
    first = _submit(None, allow=False)
    assert first.attempt == 1 and first.owner_key == f"student:{ME}"
    with pytest.raises(subs_exc.ResubmissionNotAllowedError):
        _submit(first, allow=False)
    assert _submit(first, allow=True).attempt == 2
    first.add_review(
        reviewer_id=OTHER,
        grade=None,
        comment=subs_vo.Comment(value="corrige"),
        return_for_resubmission=True,
    )
    assert first.status is subs_vo.SubmissionStatus.RETURNED
    second = _submit(first, allow=False)
    assert second.attempt == 2
    second.add_review(
        reviewer_id=OTHER,
        grade=tvo.Grade(numeric=decimal.Decimal("4.0")),
        comment=subs_vo.Comment(value=""),
        return_for_resubmission=False,
    )
    assert second.status is subs_vo.SubmissionStatus.GRADED and second.latest_grade() is not None
    with pytest.raises(subs_exc.EmptyReviewError):
        second.add_review(
            reviewer_id=OTHER,
            grade=None,
            comment=subs_vo.Comment(value=" "),
            return_for_resubmission=False,
        )


def test_submission_total_size_limit() -> None:
    with pytest.raises(subs_exc.SubmissionTooLargeError):
        _submit(None, allow=False, size=subs_vo.MAX_SUBMISSION_BYTES + 1)


# -- CSV ----------------------------------------------------------------------------


def test_csv_cell_formatting() -> None:
    assert grades_orchestrator._format(4.5, {"type": "numeric", "decimals": 1}) == "4,5"
    assert grades_orchestrator._format(3.0, {"type": "numeric", "decimals": 2}) == "3,00"
    assert grades_orchestrator._format(1, {"type": "pass_fail"}) == "Aprobado"
    assert grades_orchestrator._format(0, {"type": "pass_fail"}) == "No aprobado"
    assert grades_orchestrator._safe("=HYPERLINK()") == "'=HYPERLINK()"
    assert grades_orchestrator._safe("Ana") == "Ana"


def test_statement_md_is_stored_verbatim() -> None:
    with time_machine.travel(NOW):
        lab = _lab("none", due=None)
    assert lab.statement_md.value == "<b>tal cual</b>"
