"""Capa de aplicación de `identity.users` — ARCHITECTURE.md §6. Único módulo que llama a
`uow.repo(aggregate.User)`/`uow.repo(aggregate.EmailToken)` o a métodos de esos agregados.

Reglas de privacidad (contrato §4): registro, reenvío de verificación y recuperación
responden igual exista o no el correo — estas funciones no devuelven nada que lo distinga y
gastan tiempo de hash equivalente en la rama "no existe".

Rate limiting (contrato §6): cada función limitada cuenta el intento en una transacción
PROPIA antes de la del caso de uso, para que un fallo posterior (rollback) no lo descuente.
Por eso ninguna de ellas debe llamarse dentro de una transacción exterior.
"""

import typing
import uuid

from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import audit, mail, rate_limits
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.users.adapters import repository
from backend.identity.users.domain.model import aggregate, exceptions, value_objects
from backend.identity.users.services import dto, emails

_LOGGER = logs.get_logger()

LOGIN_RULE = rate_limits.RateLimitRule(name="login", limit=5, window_seconds=60)
REGISTER_RULE = rate_limits.RateLimitRule(name="register", limit=10, window_seconds=3600)
FORGOT_RULE = rate_limits.RateLimitRule(name="forgot", limit=3, window_seconds=3600)
RESEND_RULE = rate_limits.RateLimitRule(name="resend", limit=3, window_seconds=3600)

_SYSTEM_ACTOR = audit.Actor(id=None, label="sistema")


# --------------------------------------------------------------------------------------
# Registro y verificación
# --------------------------------------------------------------------------------------


def register(
    *,
    uow: unit_of_work.UnitOfWork,
    input_dto: dto.RegisterInputDTO,
    config: dto.UsersConfig,
    context: dto.RequestContext,
) -> None:
    """Registro abierto. Si el correo ya existe: sin verificar ⇒ reenvía la verificación;
    verificado ⇒ avisa por correo de que ya tiene cuenta. La respuesta HTTP es la misma."""
    with uow.transaction():
        uow.rate_limits.hit(REGISTER_RULE, context.ip)

    if not input_dto.accept_data_policy:
        raise exceptions.DataPolicyNotAcceptedError()
    email = value_objects.Email(value=input_dto.email)
    full_name = value_objects.FullName(value=input_dto.full_name)

    with uow.transaction():
        existing = _find_by_email(uow, email)
        if existing is None:
            user = aggregate.User.register(
                email=email,
                full_name=full_name,
                plaintext_password=input_dto.password,
                data_policy_version=config.data_policy_version,
            )
            try:
                uow.repo(aggregate.User).add(user)
            except exceptions.UserAlreadyExistsError:
                return  # carrera con otro registro del mismo correo: mismo 202
            _send_token_email(uow, user, value_objects.EmailTokenPurpose.VERIFY_EMAIL, config)
            uow.audit.add(
                _entry(
                    user,
                    value_objects.AuditAction.REGISTERED,
                    actor=_actor(user),
                    changes={
                        "data_policy_version": config.data_policy_version,
                        "ip": context.ip,
                    },
                )
            )
            _LOGGER.info("Usuario [%s] registrado", user.id)
            return

        # Rama "ya existe": mismo coste de hash que la rama nueva.
        value_objects.burn_password_check(input_dto.password)
        if not existing.is_active:
            return
        if existing.is_email_verified:
            uow.outbox.record(
                mail.EmailRequested(
                    category="already_registered",
                    message=emails.already_registered(
                        to=existing.email.value,
                        full_name=existing.full_name.value,
                        login_link=f"{config.public_base_url}/entrar",
                        reset_link=f"{config.public_base_url}/recuperar",
                    ),
                )
            )
        else:
            _send_token_email(uow, existing, value_objects.EmailTokenPurpose.VERIFY_EMAIL, config)


def verify_email(
    *, uow: unit_of_work.UnitOfWork, input_dto: dto.TokenInputDTO, config: dto.UsersConfig
) -> None:
    """Consume el token de verificación. Promueve a admin si el correo está en ADMIN_EMAILS."""
    with uow.transaction():
        token_repo = _token_repo(uow)
        token = token_repo.get_by_secret(
            input_dto.token, purpose=value_objects.EmailTokenPurpose.VERIFY_EMAIL
        )
        token.consume()
        token_repo.update(token)
        user_repo = uow.repo(aggregate.User)
        user = user_repo.get(token.user_id)
        if not user.is_active:
            raise exceptions.InvalidEmailTokenError()
        _verify_and_maybe_promote(uow, user, config)
        user_repo.update(user)


def resend_verification(
    *,
    uow: unit_of_work.UnitOfWork,
    input_dto: dto.EmailInputDTO,
    config: dto.UsersConfig,
) -> None:
    email = _email_or_none(input_dto.email)
    if email is None:
        return
    with uow.transaction():
        uow.rate_limits.hit(RESEND_RULE, email.value)
    with uow.transaction():
        user = _find_by_email(uow, email)
        if user is None or not user.is_active or user.is_email_verified:
            return
        _send_token_email(uow, user, value_objects.EmailTokenPurpose.VERIFY_EMAIL, config)


# --------------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------------


def authenticate(
    *,
    uow: unit_of_work.UnitOfWork,
    input_dto: dto.LoginInputDTO,
    context: dto.RequestContext,
) -> dto.AuthenticatedUserOutputDTO:
    """Comprueba credenciales (5 intentos/min por IP+correo). Orden de errores: credenciales
    ⇒ `invalid_credentials` (401); sólo con la contraseña correcta se revela
    `account_inactive`/`email_not_verified` (403). Re-hashea si los parámetros cambiaron."""
    email = _email_or_none(input_dto.email)
    with uow.transaction():
        uow.rate_limits.hit(LOGIN_RULE, f"{context.ip}|{email.value if email else '-'}")
    if email is None:
        value_objects.burn_password_check(input_dto.password)
        raise exceptions.InvalidCredentialsError()

    failure: exceptions.InvalidCredentialsError | None = None
    with uow.transaction():
        user_repo = uow.repo(aggregate.User)
        user = _find_by_email(uow, email)
        if user is None:
            value_objects.burn_password_check(input_dto.password)
            raise exceptions.InvalidCredentialsError()
        if not user.verify_password(input_dto.password):
            # Se audita y se confirma; el error se lanza fuera de la transacción.
            uow.audit.add(
                _entry(
                    user,
                    value_objects.AuditAction.LOGIN_FAILED,
                    actor=_actor(user),
                    changes={"ip": context.ip},
                )
            )
            failure = exceptions.InvalidCredentialsError()
        else:
            user.ensure_can_log_in()
            if user.rehash_password_if_needed(input_dto.password):
                user_repo.update(user)
                uow.audit.add(
                    _entry(user, value_objects.AuditAction.PASSWORD_REHASHED, actor=_SYSTEM_ACTOR)
                )
            uow.audit.add(
                _entry(
                    user,
                    value_objects.AuditAction.LOGIN_SUCCEEDED,
                    actor=_actor(user),
                    changes={"ip": context.ip, "user_agent": context.user_agent[:200]},
                )
            )
    if failure is not None:
        raise failure
    return dto.AuthenticatedUserOutputDTO(
        me=dto.MeOutputDTO.from_entity(user), claims=dto.TokenClaimsOutputDTO.from_entity(user)
    )


def get_token_claims(*, uow: unit_of_work.UnitOfWork, user_id: str) -> dto.TokenClaimsOutputDTO:
    with uow.transaction():
        user = uow.repo(aggregate.User).get(_user_id(user_id))
    return dto.TokenClaimsOutputDTO.from_entity(user)


# --------------------------------------------------------------------------------------
# Recuperación de contraseña
# --------------------------------------------------------------------------------------


def request_password_reset(
    *,
    uow: unit_of_work.UnitOfWork,
    input_dto: dto.EmailInputDTO,
    config: dto.UsersConfig,
    context: dto.RequestContext,
) -> None:
    """3 solicitudes/h por correo. Sólo el último enlace emitido es válido."""
    email = _email_or_none(input_dto.email)
    if email is None:
        return
    with uow.transaction():
        uow.rate_limits.hit(FORGOT_RULE, email.value)
    with uow.transaction():
        user = _find_by_email(uow, email)
        if user is None or not user.is_active:
            return
        _send_token_email(uow, user, value_objects.EmailTokenPurpose.PASSWORD_RESET, config)
        uow.audit.add(
            _entry(
                user,
                value_objects.AuditAction.PASSWORD_RESET_REQUESTED,
                actor=_actor(user),
                changes={"ip": context.ip},
            )
        )


def reset_password(
    *,
    uow: unit_of_work.UnitOfWork,
    input_dto: dto.ResetPasswordInputDTO,
    config: dto.UsersConfig,
) -> dto.TokenClaimsOutputDTO:
    """Consume el token, cambia la contraseña y sube `credentials_version`. Revocar las
    sesiones es responsabilidad del orquestador (`identity.services.reset_password_orchestrator`).
    Restablecer por enlace prueba que el correo es suyo: también lo marca verificado."""
    with uow.transaction():
        token_repo = _token_repo(uow)
        token = token_repo.get_by_secret(
            input_dto.token, purpose=value_objects.EmailTokenPurpose.PASSWORD_RESET
        )
        token.consume()
        user_repo = uow.repo(aggregate.User)
        user = user_repo.get(token.user_id)
        if not user.is_active:
            raise exceptions.InvalidEmailTokenError()
        user.change_password(input_dto.password)
        _verify_and_maybe_promote(uow, user, config)
        token_repo.update(token)
        token_repo.invalidate_open(
            user_id=user.id, purpose=value_objects.EmailTokenPurpose.PASSWORD_RESET
        )
        user_repo.update(user)
        uow.audit.add(
            _entry(
                user,
                value_objects.AuditAction.PASSWORD_RESET,
                actor=_actor(user),
                changes={"credentials_version": user.credentials_version},
            )
        )
    return dto.TokenClaimsOutputDTO.from_entity(user)


# --------------------------------------------------------------------------------------
# Perfil
# --------------------------------------------------------------------------------------


def get_me(
    *, uow: unit_of_work.UnitOfWork, user_id: str, credentials_version: int
) -> dto.MeOutputDTO:
    """`credentials_version` es el `ver` del access: si ya no coincide (contraseña cambiada)
    o el usuario fue desactivado, la sesión del navegador deja de valer (401)."""
    with uow.transaction():
        try:
            user = uow.repo(aggregate.User).get(_user_id(user_id))
        except exceptions.UserNotFoundError as exc:
            raise exceptions.StaleCredentialsError() from exc
    if not user.is_active or user.credentials_version != credentials_version:
        raise exceptions.StaleCredentialsError()
    return dto.MeOutputDTO.from_entity(user)


def update_me(
    *, uow: unit_of_work.UnitOfWork, user_id: str, input_dto: dto.UpdateMeInputDTO
) -> dto.MeOutputDTO:
    with uow.transaction():
        user_repo = uow.repo(aggregate.User)
        user = user_repo.get(_user_id(user_id))
        old_name = user.full_name.value
        user.rename(value_objects.FullName(value=input_dto.full_name))
        if user.full_name.value != old_name:
            user_repo.update(user)
            uow.audit.add(
                _entry(
                    user,
                    value_objects.AuditAction.PROFILE_UPDATED,
                    actor=_actor(user),
                    changes={"full_name": {"old": old_name, "new": user.full_name.value}},
                )
            )
    return dto.MeOutputDTO.from_entity(user)


def change_password(
    *, uow: unit_of_work.UnitOfWork, user_id: str, input_dto: dto.ChangePasswordInputDTO
) -> dto.TokenClaimsOutputDTO:
    """Exige la contraseña actual. Sube `credentials_version`; el orquestador cierra las
    demás sesiones y re-emite el access de la actual."""
    with uow.transaction():
        user_repo = uow.repo(aggregate.User)
        user = user_repo.get(_user_id(user_id))
        if not user.verify_password(input_dto.current):
            raise exceptions.CurrentPasswordMismatchError()
        user.change_password(input_dto.new)
        user_repo.update(user)
        uow.audit.add(
            _entry(
                user,
                value_objects.AuditAction.PASSWORD_CHANGED,
                actor=_actor(user),
                changes={"credentials_version": user.credentials_version},
            )
        )
    return dto.TokenClaimsOutputDTO.from_entity(user)


def deactivate_user(
    *, uow: unit_of_work.UnitOfWork, user_id: str, actor: audit.Actor
) -> dto.MeOutputDTO:
    """El orquestador revoca además todas las sesiones."""
    with uow.transaction():
        user_repo = uow.repo(aggregate.User)
        user = user_repo.get(_user_id(user_id))
        user.deactivate()
        user_repo.update(user)
        uow.audit.add(_entry(user, value_objects.AuditAction.DEACTIVATED, actor=actor))
    return dto.MeOutputDTO.from_entity(user)


def delete_expired_email_tokens(*, uow: unit_of_work.UnitOfWork) -> int:
    """Housekeeping (worker): borra tokens caducados hace más de un día."""
    cutoff = base_value_objects.PosixTime(
        microseconds=base_value_objects.PosixTime.now().microseconds - 86_400 * 1_000_000
    )
    with uow.transaction():
        return _token_repo(uow).delete_expired(older_than=cutoff)


# --------------------------------------------------------------------------------------
# Auxiliares
# --------------------------------------------------------------------------------------


def _verify_and_maybe_promote(
    uow: unit_of_work.UnitOfWork, user: aggregate.User, config: dto.UsersConfig
) -> None:
    was_verified = user.is_email_verified
    old_role = user.verify_email(admin_emails=config.admin_emails)
    if not was_verified:
        uow.audit.add(_entry(user, value_objects.AuditAction.EMAIL_VERIFIED, actor=_actor(user)))
    if old_role is not None:
        uow.audit.add(
            _entry(
                user,
                value_objects.AuditAction.ROLE_CHANGED,
                actor=audit.Actor(id=None, label="ADMIN_EMAILS"),
                changes={"role": {"old": old_role.value, "new": user.role.value}},
            )
        )


def _send_token_email(
    uow: unit_of_work.UnitOfWork,
    user: aggregate.User,
    purpose: value_objects.EmailTokenPurpose,
    config: dto.UsersConfig,
) -> None:
    token_repo = _token_repo(uow)
    token_repo.invalidate_open(user_id=user.id, purpose=purpose)
    token, secret = aggregate.EmailToken.issue(user_id=user.id, purpose=purpose)
    token_repo.add(token)
    if purpose is value_objects.EmailTokenPurpose.VERIFY_EMAIL:
        message = emails.verification(
            to=user.email.value,
            full_name=user.full_name.value,
            link=f"{config.public_base_url}/verificar?t={secret}",
        )
    else:
        message = emails.password_reset(
            to=user.email.value,
            full_name=user.full_name.value,
            link=f"{config.public_base_url}/restablecer?t={secret}",
        )
    uow.outbox.record(mail.EmailRequested(category=purpose.value, message=message))


def _entry(
    user: aggregate.User,
    action: value_objects.AuditAction,
    *,
    actor: audit.Actor,
    changes: dict[str, typing.Any] | None = None,
) -> audit.AuditEntry:
    return audit.AuditEntry(
        actor=actor,
        action=action.value,
        aggregate_type=value_objects.AuditAggregateType.USER.value,
        aggregate_id=str(user.id),
        changes=changes or {},
    )


def _actor(user: aggregate.User) -> audit.Actor:
    return audit.Actor(id=str(user.id), label=user.email.value)


def _user_id(user_id: str) -> identity_value_objects.UserId:
    try:
        return identity_value_objects.UserId(value=uuid.UUID(user_id))
    except ValueError as exc:
        raise exceptions.UserNotFoundError(identifier=user_id) from exc


def _email_or_none(raw: str) -> value_objects.Email | None:
    try:
        return value_objects.Email(value=raw)
    except Exception:  # noqa: BLE001 — correo inválido: se trata como inexistente
        return None


def _find_by_email(
    uow: unit_of_work.UnitOfWork, email: value_objects.Email
) -> aggregate.User | None:
    try:
        return _user_repo(uow).get_by_email(email)
    except exceptions.UserNotFoundError:
        return None


def _user_repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultUserRepository:
    """`uow.repo(...)` devuelve el puerto genérico; `get_by_email` es una consulta propia
    del repositorio concreto (ARCHITECTURE.md §7)."""
    return typing.cast(repository.DefaultUserRepository, uow.repo(aggregate.User))


def _token_repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultEmailTokenRepository:
    return typing.cast(repository.DefaultEmailTokenRepository, uow.repo(aggregate.EmailToken))
