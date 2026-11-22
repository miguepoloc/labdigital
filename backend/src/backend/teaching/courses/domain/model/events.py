from backend.commons.domain import events as domain_events
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.courses.domain.model import value_objects


class CourseCreated(domain_events.DomainEvent):
    course_id: teaching_value_objects.CourseId
    owner_id: teaching_value_objects.UserRef


class JoinRequested(domain_events.DomainEvent):
    course_id: teaching_value_objects.CourseId
    user_id: teaching_value_objects.UserRef


class MembershipStatusChanged(domain_events.DomainEvent):
    course_id: teaching_value_objects.CourseId
    user_id: teaching_value_objects.UserRef
    old_status: value_objects.MembershipStatus
    new_status: value_objects.MembershipStatus
