from backend.commons.domain import events as domain_events
from backend.projects.projects.domain.model import value_objects


class ProjectCreated(domain_events.DomainEvent):
    project_id: value_objects.ProjectId
    owner_id: value_objects.OwnerId


class ProjectDeleted(domain_events.DomainEvent):
    project_id: value_objects.ProjectId
