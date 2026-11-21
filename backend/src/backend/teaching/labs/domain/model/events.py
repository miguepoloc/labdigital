from backend.commons.domain import events as domain_events
from backend.teaching.commons import value_objects as teaching_value_objects


class LabCreated(domain_events.DomainEvent):
    lab_id: teaching_value_objects.LabId
    course_id: teaching_value_objects.CourseId


class LabPublished(domain_events.DomainEvent):
    lab_id: teaching_value_objects.LabId
    course_id: teaching_value_objects.CourseId


class TeamMembersChanged(domain_events.DomainEvent):
    team_id: teaching_value_objects.TeamId
    lab_id: teaching_value_objects.LabId
    members: list[teaching_value_objects.UserRef]
