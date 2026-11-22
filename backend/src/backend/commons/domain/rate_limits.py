"""Vocabulario de rate limiting compartido — la regla es un valor puro; el contador vive en
`commons.adapters.rate_limit` (Postgres)."""

from backend.commons.domain import value_objects


class RateLimitRule(value_objects.ValueObject):
    name: str
    limit: int
    window_seconds: int


class BackoffRule(value_objects.ValueObject):
    """Retardo creciente tras fallos CONSECUTIVOS (plan §Autenticación: "login 5/min por
    IP+correo con retardo creciente"). Los primeros `free_failures` fallos no esperan; desde
    ahí, tras el fallo k-ésimo hay que esperar `base_seconds ** (k - free_failures)`
    segundos (2, 4, 8, … con los valores por defecto), con tope `max_seconds`. Un acierto
    reinicia el contador; también se reinicia si pasan `reset_after_seconds` sin fallos."""

    name: str
    free_failures: int = 2
    base_seconds: int = 2
    max_seconds: int = 900
    reset_after_seconds: int = 3600

    def delay_after(self, failures: int) -> int:
        if failures <= self.free_failures:
            return 0
        exponent = failures - self.free_failures
        return int(min(self.base_seconds**exponent, self.max_seconds))
