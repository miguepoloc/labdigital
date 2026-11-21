from typing import Self

from backend.commons.domain import aggregates
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.users.domain.model import events, value_objects


class User(aggregates.AggregateRoot[value_objects.UserId]):
    email: value_objects.Email
    full_name: str
    hashed_password: value_objects.HashedPassword
    is_active: bool

    @classmethod
    def register(
        cls, *, email: value_objects.Email, full_name: str, plaintext_password: str
    ) -> Self:
        now = base_value_objects.PosixTime.now()
        user = cls(
            id=value_objects.UserId.new(),
            email=email,
            full_name=full_name,
            hashed_password=value_objects.HashedPassword.hash_plaintext(plaintext_password),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        user.record_event(events.UserRegistered(user_id=user.id, email=user.email))
        return user

    def verify_password(self, plaintext_password: str) -> bool:
        """Pure check — no I/O, no side effects. The application service decides what to
        do with the result (issue tokens, raise InvalidCredentialsError)."""
        return self.hashed_password.matches(plaintext_password)

    def deactivate(self) -> None:
        """Idempotent — deactivating an already-inactive user is a no-op, not an error
        (same reasoning as ARCHITECTURE.md §12.1's suspend/resume exemption)."""
        if not self.is_active:
            return
        self.is_active = False
        self.touch()
        self.record_event(events.UserDeactivated(user_id=self.id))
