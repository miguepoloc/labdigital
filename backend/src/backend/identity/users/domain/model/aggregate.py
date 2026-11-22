"""Agregados de `identity.users`: `User` y `EmailToken`.

`EmailToken` es un segundo agregado en el mismo subcontexto (desviación consciente de
"un subcontexto = un agregado"): sólo existe para un `User`, se crea y consume siempre
dentro de un caso de uso de `users`, y separarlo en otro subcontexto obligaría a un
orquestador por cada flujo de verificación/recuperación sin ganar nada.
"""

import datetime
from typing import Self

from backend.commons.domain import aggregates
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.users.domain.model import events, exceptions, rules, value_objects

VERIFY_EMAIL_TTL = datetime.timedelta(hours=24)
PASSWORD_RESET_TTL = datetime.timedelta(minutes=30)


class User(aggregates.AggregateRoot[identity_value_objects.UserId]):
    email: value_objects.Email
    full_name: value_objects.FullName
    hashed_password: value_objects.HashedPassword
    role: identity_value_objects.Role
    email_verified_at: base_value_objects.PosixTime | None
    credentials_version: int
    is_active: bool
    data_policy: value_objects.DataPolicyAcceptance

    @classmethod
    def register(
        cls,
        *,
        email: value_objects.Email,
        full_name: value_objects.FullName,
        plaintext_password: str,
        data_policy_version: str,
    ) -> Self:
        """La contraseña ya debe cumplir `rules.PasswordPolicy` (se comprueba aquí igual)."""
        rules.PasswordPolicy(plaintext_password).check()
        now = base_value_objects.PosixTime.now()
        user = cls(
            id=identity_value_objects.UserId.new(),
            email=email,
            full_name=full_name,
            hashed_password=value_objects.HashedPassword.hash_plaintext(plaintext_password),
            role=identity_value_objects.Role.USER,
            email_verified_at=None,
            credentials_version=1,
            is_active=True,
            data_policy=value_objects.DataPolicyAcceptance(
                version=data_policy_version, accepted_at=now
            ),
            created_at=now,
            updated_at=now,
        )
        user.record_event(events.UserRegistered(user_id=user.id))
        return user

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    def verify_email(self, *, admin_emails: frozenset[str]) -> identity_value_objects.Role | None:
        """Marca el correo como verificado (idempotente). Si el correo está en
        `ADMIN_EMAILS` y aún no es admin, lo promueve. Devuelve el rol anterior si cambió."""
        changed = False
        if self.email_verified_at is None:
            self.email_verified_at = base_value_objects.PosixTime.now()
            self.record_event(events.EmailVerified(user_id=self.id))
            changed = True
        old_role: identity_value_objects.Role | None = None
        if self.email.value in admin_emails and self.role is not identity_value_objects.Role.ADMIN:
            old_role = self.role
            self.change_role(identity_value_objects.Role.ADMIN)
            changed = True
        if changed:
            self.touch()
        return old_role

    def change_role(self, new_role: identity_value_objects.Role) -> None:
        if new_role is self.role:
            return
        old_role, self.role = self.role, new_role
        self.touch()
        self.record_event(events.RoleChanged(user_id=self.id, old_role=old_role, new_role=new_role))

    def verify_password(self, plaintext_password: str) -> bool:
        """Comprobación pura; el servicio decide qué hacer con el resultado."""
        return self.hashed_password.matches(plaintext_password)

    def rehash_password_if_needed(self, plaintext_password: str) -> bool:
        """Llamar sólo tras `verify_password` correcto. No cambia `credentials_version`: la
        contraseña es la misma, sólo cambia el hash."""
        if not self.hashed_password.needs_rehash():
            return False
        self.hashed_password = value_objects.HashedPassword.hash_plaintext(plaintext_password)
        self.touch()
        return True

    def change_password(self, new_plaintext_password: str) -> None:
        """Sube `credentials_version`: los access emitidos antes dejan de corresponder."""
        rules.PasswordPolicy(new_plaintext_password).check()
        self.hashed_password = value_objects.HashedPassword.hash_plaintext(new_plaintext_password)
        self.credentials_version += 1
        self.touch()
        self.record_event(
            events.PasswordChanged(user_id=self.id, credentials_version=self.credentials_version)
        )

    def rename(self, full_name: value_objects.FullName) -> None:
        if full_name == self.full_name:
            return
        self.full_name = full_name
        self.touch()

    def ensure_can_log_in(self) -> None:
        if not self.is_active:
            raise exceptions.AccountInactiveError()
        if not self.is_email_verified:
            raise exceptions.EmailNotVerifiedError()

    def activate(self) -> bool:
        """Idempotente; devuelve si cambió algo."""
        if self.is_active:
            return False
        self.is_active = True
        self.touch()
        self.record_event(events.UserActivated(user_id=self.id))
        return True

    def deactivate(self) -> None:
        """Idempotente."""
        if not self.is_active:
            return
        self.is_active = False
        self.touch()
        self.record_event(events.UserDeactivated(user_id=self.id))


class EmailToken(aggregates.AggregateRoot[value_objects.EmailTokenId]):
    """Token de un solo uso enviado por correo. Sólo se guarda el hash del secreto."""

    user_id: identity_value_objects.UserId
    purpose: value_objects.EmailTokenPurpose
    token_hash: str
    expires_at: base_value_objects.PosixTime
    used_at: base_value_objects.PosixTime | None

    @classmethod
    def issue(
        cls, *, user_id: identity_value_objects.UserId, purpose: value_objects.EmailTokenPurpose
    ) -> tuple[Self, str]:
        """Devuelve el agregado y el secreto en claro (sólo para el enlace del correo)."""
        secret = value_objects.new_token_secret()
        now = base_value_objects.PosixTime.now()
        ttl = (
            VERIFY_EMAIL_TTL
            if purpose is value_objects.EmailTokenPurpose.VERIFY_EMAIL
            else PASSWORD_RESET_TTL
        )
        token = cls(
            id=value_objects.EmailTokenId.new(),
            user_id=user_id,
            purpose=purpose,
            token_hash=value_objects.hash_token_secret(secret),
            expires_at=base_value_objects.PosixTime.from_datetime(now.to_datetime() + ttl),
            used_at=None,
            created_at=now,
            updated_at=now,
        )
        return token, secret

    def consume(self) -> None:
        """Lanza `InvalidEmailTokenError` si ya se usó o caducó."""
        now = base_value_objects.PosixTime.now()
        if self.used_at is not None or self.expires_at <= now:
            raise exceptions.InvalidEmailTokenError()
        self.used_at = now
        self.touch()
