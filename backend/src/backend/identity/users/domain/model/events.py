from backend.commons.domain import events as domain_events
from backend.identity.users.domain.model import value_objects


class UserRegistered(domain_events.DomainEvent):
    """Internal only — no other bounded context needs to know a user just registered."""

    user_id: value_objects.UserId
    email: value_objects.Email


class UserDeactivated(domain_events.IntegrationEvent):
    """Crosses into commerce (ARCHITECTURE.md §10.3/§19): orders reacts by cancelling this
    user's pending orders."""

    user_id: value_objects.UserId
