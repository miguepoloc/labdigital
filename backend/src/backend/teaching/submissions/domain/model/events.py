from backend.commons.domain import events as domain_events
from backend.teaching.commons import value_objects as teaching_value_objects
from backend.teaching.submissions.domain.model import value_objects


class LabSubmitted(domain_events.DomainEvent):
    submission_id: value_objects.SubmissionId
    lab_id: teaching_value_objects.LabId
    attempt: int
    is_late: bool


class SubmissionReviewed(domain_events.DomainEvent):
    submission_id: value_objects.SubmissionId
    status: value_objects.SubmissionStatus
