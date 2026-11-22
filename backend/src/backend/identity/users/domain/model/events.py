from backend.commons.domain import events as domain_events
from backend.identity.commons import value_objects as identity_value_objects


class UserRegistered(domain_events.DomainEvent):
    user_id: identity_value_objects.UserId


class EmailVerified(domain_events.DomainEvent):
    user_id: identity_value_objects.UserId


class PasswordChanged(domain_events.DomainEvent):
    user_id: identity_value_objects.UserId
    credentials_version: int


class RoleChanged(domain_events.DomainEvent):
    user_id: identity_value_objects.UserId
    old_role: identity_value_objects.Role
    new_role: identity_value_objects.Role


class UserDeactivated(domain_events.IntegrationEvent):
    user_id: identity_value_objects.UserId


class UserActivated(domain_events.DomainEvent):
    user_id: identity_value_objects.UserId
