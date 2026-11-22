"""Agregados de `teaching.labs`: `Lab` y `Team` (LD-5).

`Team` es un agregado aparte (como `Membership` respecto a `Course`): los estudiantes se
unen y salen a la vez de equipos distintos. "Un estudiante, un equipo por lab" lo garantiza
Postgres (`team_members` único por `(lab_id, user_id)`); el tamaño máximo, la versión
optimista del equipo (dos uniones simultáneas al último hueco: una recibe 409)."""

from typing import Any, Self

from backend.commons.domain import aggregates
from backend.commons.domain import value_objects as base_value_objects
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.labs.domain.model import events, exceptions, value_objects


class Lab(aggregates.AggregateRoot[teaching_value_objects.LabId]):
    course_id: teaching_value_objects.CourseId
    created_by: teaching_value_objects.UserRef
    title: value_objects.LabTitle
    statement_md: value_objects.StatementMd
    module: value_objects.LabModule
    schedule: value_objects.Schedule
    team_setup: value_objects.TeamSetup
    grade_scale: teaching_value_objects.GradeScale
    allow_resubmission: bool
    published_at: base_value_objects.PosixTime | None = None

    @classmethod
    def create(
        cls,
        *,
        course_id: teaching_value_objects.CourseId,
        created_by: teaching_value_objects.UserRef,
        title: value_objects.LabTitle,
        statement_md: value_objects.StatementMd,
        module: value_objects.LabModule,
        schedule: value_objects.Schedule,
        team_setup: value_objects.TeamSetup,
        grade_scale: teaching_value_objects.GradeScale,
        allow_resubmission: bool,
    ) -> Self:
        now = base_value_objects.PosixTime.now()
        lab = cls(
            id=teaching_value_objects.LabId.new(),
            course_id=course_id,
            created_by=created_by,
            title=title,
            statement_md=statement_md,
            module=module,
            schedule=schedule,
            team_setup=team_setup,
            grade_scale=grade_scale,
            allow_resubmission=allow_resubmission,
            created_at=now,
            updated_at=now,
        )
        lab.record_event(events.LabCreated(lab_id=lab.id, course_id=course_id))
        return lab

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    @property
    def is_team(self) -> bool:
        return self.team_setup.team_mode is value_objects.TeamMode.TEAM

    def apply_changes(self, changes: dict[str, Any]) -> dict[str, Any]:
        """`changes` ya validados (value objects). Publicado ⇒ `team_mode`/`max_team_size`
        (hay equipos formados) y `grade_scale` (puede haber notas) quedan fijos. Devuelve
        un resumen para auditoría."""
        applied: dict[str, Any] = {}
        for field, new in changes.items():
            old = getattr(self, field)
            if new == old:
                continue
            if self.is_published and field in ("team_setup", "grade_scale", "module"):
                raise exceptions.LabPublishedError(field)
            setattr(self, field, new)
            applied[field] = "changed" if field == "statement_md" else str(new)
        if applied:
            self.touch()
        return applied

    def publish(self) -> bool:
        if self.is_published:
            return False
        self.published_at = base_value_objects.PosixTime.now()
        self.touch()
        self.record_event(events.LabPublished(lab_id=self.id, course_id=self.course_id))
        return True

    def ensure_team_lab(self) -> int:
        if not self.is_team or self.team_setup.max_team_size is None:
            raise exceptions.NotATeamLabError()
        return self.team_setup.max_team_size

    def evaluate_submission(self, *, now: base_value_objects.PosixTime, returned: bool) -> bool:
        """Decide si se admite una entrega ahora y si es tardía (`is_late`).

        - antes de `opens_at` ⇒ 409 `lab_not_open`;
        - `strict` y pasó `due_at` ⇒ 409 `deadline_passed`, SALVO que el docente haya
          devuelto la última entrega para corregir (`returned`): esa re-entrega se admite y
          queda marcada tardía;
        - `late_marked` ⇒ se admite, tardía si pasó `due_at`; `none` ⇒ nunca tardía."""
        schedule = self.schedule
        if schedule.opens_at is not None and now < schedule.opens_at:
            raise exceptions.LabNotOpenError()
        if schedule.deadline_policy is value_objects.DeadlinePolicy.NONE or schedule.due_at is None:
            return False
        late = now > schedule.due_at
        if (
            late
            and schedule.deadline_policy is value_objects.DeadlinePolicy.STRICT
            and not returned
        ):
            raise exceptions.DeadlinePassedError()
        return late


class Team(aggregates.AggregateRoot[teaching_value_objects.TeamId]):
    lab_id: teaching_value_objects.LabId
    course_id: teaching_value_objects.CourseId
    name: value_objects.TeamName
    join_code: value_objects.TeamJoinCode
    locked: bool = False
    members: list[teaching_value_objects.UserRef]

    @classmethod
    def create(
        cls,
        *,
        lab_id: teaching_value_objects.LabId,
        course_id: teaching_value_objects.CourseId,
        name: value_objects.TeamName,
        creator: teaching_value_objects.UserRef,
    ) -> Self:
        now = base_value_objects.PosixTime.now()
        team = cls(
            id=teaching_value_objects.TeamId.new(),
            lab_id=lab_id,
            course_id=course_id,
            name=name,
            join_code=value_objects.TeamJoinCode.new(),
            members=[creator],
            created_at=now,
            updated_at=now,
        )
        team._changed()
        return team

    def has_member(self, user_id: teaching_value_objects.UserRef) -> bool:
        return user_id in self.members

    def join(self, user_id: teaching_value_objects.UserRef, *, max_size: int) -> None:
        if self.locked:
            raise exceptions.TeamLockedError()
        if self.has_member(user_id):
            return
        if len(self.members) >= max_size:
            raise exceptions.TeamFullError(max_size)
        self.members = [*self.members, user_id]
        self._changed()

    def leave(self, user_id: teaching_value_objects.UserRef) -> None:
        if self.locked:
            raise exceptions.TeamLockedError()
        if not self.has_member(user_id):
            raise exceptions.NotInTeamError()
        self.members = [m for m in self.members if m != user_id]
        self._changed()

    def set_members(self, members: list[teaching_value_objects.UserRef], *, max_size: int) -> None:
        """Reasignación del docente: vale también con el equipo bloqueado."""
        unique = list(dict.fromkeys(members))
        if len(unique) > max_size:
            raise exceptions.TeamTooLargeError(max_size)
        if unique != self.members:
            self.members = unique
            self._changed()

    def remove_member_by_teacher(self, user_id: teaching_value_objects.UserRef) -> None:
        """Al mover a alguien a otro equipo (reasignación del docente)."""
        if self.has_member(user_id):
            self.members = [m for m in self.members if m != user_id]
            self._changed()

    def set_locked(self, locked: bool) -> bool:
        if self.locked == locked:
            return False
        self.locked = locked
        self.touch()
        return True

    def _changed(self) -> None:
        self.touch()
        self.record_event(
            events.TeamMembersChanged(
                team_id=self.id, lab_id=self.lab_id, members=list(self.members)
            )
        )
