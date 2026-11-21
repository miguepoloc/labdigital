"""Vocabulario de rate limiting compartido — la regla es un valor puro; el contador vive en
`commons.adapters.rate_limit` (Postgres)."""

from backend.commons.domain import value_objects


class RateLimitRule(value_objects.ValueObject):
    name: str
    limit: int
    window_seconds: int
