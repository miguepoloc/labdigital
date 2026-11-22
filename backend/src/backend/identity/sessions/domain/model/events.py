from backend.commons.domain import events as domain_events
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.sessions.domain.model import value_objects


class SessionStarted(domain_events.DomainEvent):
    session_id: value_objects.SessionId
    user_id: identity_value_objects.UserId


class SessionRevoked(domain_events.DomainEvent):
    session_id: value_objects.SessionId
    user_id: identity_value_objects.UserId
    reason: value_objects.RevokeReason


class RefreshTokenReuseDetected(domain_events.DomainEvent):
    """Un refresh ya rotado se volvió a presentar: probable robo. La familia se revoca."""

    session_id: value_objects.SessionId
    user_id: identity_value_objects.UserId
    token_id: value_objects.RefreshTokenId
