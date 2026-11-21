"""Agregados de `teaching.courses`: `Course` y `Membership`.

Dos agregados y no uno: cada inscripción cambia sola (un estudiante pide entrar, el docente
aprueba a otro) y meterlas todas en `Course` haría que dos solicitudes simultáneas choquen
por la versión optimista del curso. `Membership` tiene unicidad `(course_id, user_id)` en
Postgres. Quien crea el curso es su `docente` (membresía activa con ese rol)."""

from typing import Self

from backend.commons.domain import aggregates
from backend.commons.domain import value_objects as base_value_objects
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.domain.model import events, exceptions, value_objects


class Course(aggregates.AggregateRoot[teaching_value_objects.CourseId]):
    owner_id: teaching_value_objects.UserRef
    name: value_objects.CourseName
    period: value_objects.Period
    description: value_objects.Description
    join_code: value_objects.JoinCode
    archived_at: base_value_objects.PosixTime | None = None

    @classmethod
    def create(
        cls,
        *,
        owner_id: teaching_value_objects.UserRef,
        name: value_objects.CourseName,
        period: value_objects.Period,
        description: value_objects.Description,
    ) -> Self:
        now = base_value_objects.PosixTime.now()
        course = cls(
            id=teaching_value_objects.CourseId.new(),
            owner_id=owner_id,
            name=name,
            period=period,
            description=description,
            join_code=value_objects.JoinCode.new(),
            created_at=now,
            updated_at=now,
        )
        course.record_event(events.CourseCreated(course_id=course.id, owner_id=owner_id))
        return course

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def is_teacher(self, user_id: teaching_value_objects.UserRef) -> bool:
        return self.owner_id == user_id

    def ensure_open(self) -> None:
        if self.is_archived:
            raise exceptions.CourseArchivedError()

    def update(
        self,
        *,
        name: value_objects.CourseName | None,
        period: value_objects.Period | None,
        description: value_objects.Description | None,
    ) -> dict[str, dict[str, str]]:
        """Devuelve los cambios (para auditoría). Un curso archivado no se edita."""
        changes: dict[str, dict[str, str]] = {}
        for field, new in (("name", name), ("period", period), ("description", description)):
            if new is None:
                continue
            old = getattr(self, field)
            if new != old:
                self.ensure_open()
                changes[field] = {"old": old.value, "new": new.value}
                setattr(self, field, new)
        if changes:
            self.touch()
        return changes

    def archive(self) -> bool:
        if self.is_archived:
            return False
        self.archived_at = base_value_objects.PosixTime.now()
        self.touch()
        return True

    def unarchive(self) -> bool:
        if not self.is_archived:
            return False
        self.archived_at = None
        self.touch()
        return True

    def rotate_join_code(self) -> None:
        self.ensure_open()
        self.join_code = value_objects.JoinCode.new()
        self.touch()


class Membership(aggregates.AggregateRoot[value_objects.MembershipId]):
    course_id: teaching_value_objects.CourseId
    user_id: teaching_value_objects.UserRef
    role: value_objects.MembershipRole
    status: value_objects.MembershipStatus

    @classmethod
    def for_teacher(
        cls, *, course_id: teaching_value_objects.CourseId, user_id: teaching_value_objects.UserRef
    ) -> Self:
        return cls._new(
            course_id,
            user_id,
            value_objects.MembershipRole.DOCENTE,
            value_objects.MembershipStatus.ACTIVE,
        )

    @classmethod
    def request(
        cls, *, course_id: teaching_value_objects.CourseId, user_id: teaching_value_objects.UserRef
    ) -> Self:
        membership = cls._new(
            course_id,
            user_id,
            value_objects.MembershipRole.ESTUDIANTE,
            value_objects.MembershipStatus.PENDING,
        )
        membership.record_event(events.JoinRequested(course_id=course_id, user_id=user_id))
        return membership

    @classmethod
    def _new(
        cls,
        course_id: teaching_value_objects.CourseId,
        user_id: teaching_value_objects.UserRef,
        role: value_objects.MembershipRole,
        status: value_objects.MembershipStatus,
    ) -> Self:
        now = base_value_objects.PosixTime.now()
        return cls(
            id=value_objects.MembershipId.new(),
            course_id=course_id,
            user_id=user_id,
            role=role,
            status=status,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_teacher(self) -> bool:
        return self.role is value_objects.MembershipRole.DOCENTE

    @property
    def is_active_student(self) -> bool:
        return (
            self.role is value_objects.MembershipRole.ESTUDIANTE
            and self.status is value_objects.MembershipStatus.ACTIVE
        )

    def rerequest(self) -> bool:
        """Volver a usar el código tras ser rechazado o retirado ⇒ nueva solicitud pendiente.
        Pendiente o activo ⇒ no cambia nada (idempotente)."""
        if self.status in (
            value_objects.MembershipStatus.REJECTED,
            value_objects.MembershipStatus.REMOVED,
        ):
            self._change(value_objects.MembershipStatus.PENDING)
            self.record_event(events.JoinRequested(course_id=self.course_id, user_id=self.user_id))
            return True
        return False

    def decide(self, decision: value_objects.MembershipDecision) -> bool:
        """Transiciones del docente. Devuelve si cambió algo.

        approve: pendiente/rechazada/retirada → activa · reject: pendiente → rechazada ·
        remove: pendiente/activa → retirada. Al docente no se le aplica ninguna."""
        if self.is_teacher:
            raise exceptions.InvalidMembershipTransitionError(
                "El docente del curso no se puede aprobar, rechazar ni retirar."
            )
        status = value_objects.MembershipStatus
        allowed = {
            value_objects.MembershipDecision.APPROVE: (
                {status.PENDING, status.REJECTED, status.REMOVED},
                status.ACTIVE,
            ),
            value_objects.MembershipDecision.REJECT: ({status.PENDING}, status.REJECTED),
            value_objects.MembershipDecision.REMOVE: (
                {status.PENDING, status.ACTIVE},
                status.REMOVED,
            ),
        }
        sources, target = allowed[decision]
        if self.status is target:
            return False
        if self.status not in sources:
            raise exceptions.InvalidMembershipTransitionError(
                f"No se puede pasar de {self.status.value} a {target.value}."
            )
        self._change(target)
        return True

    def _change(self, new_status: value_objects.MembershipStatus) -> None:
        old, self.status = self.status, new_status
        self.touch()
        self.record_event(
            events.MembershipStatusChanged(
                course_id=self.course_id,
                user_id=self.user_id,
                old_status=old,
                new_status=new_status,
            )
        )
