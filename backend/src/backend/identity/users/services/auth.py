"""Application layer for identity/users — ARCHITECTURE.md §6. The only module allowed to
call `uow.repo(aggregate.User)` or a User command method. No `_publish_events()` helper here
— `DefaultUserRepository.add`/`.update` do that internally (ARCHITECTURE.md §7/§11.2)."""

import typing

from backend.commons.adapters import authentication, logs, unit_of_work
from backend.commons.domain import audit
from backend.identity.users.adapters import refresh_tokens, repository
from backend.identity.users.domain.model import aggregate, exceptions, value_objects
from backend.identity.users.services import dto

_LOGGER = logs.get_logger()


def register_user(
    *, uow: unit_of_work.UnitOfWork, input_dto: dto.RegisterUserInputDTO
) -> dto.UserOutputDTO:
    with uow.transaction():
        email = value_objects.Email(value=input_dto.email)
        if _email_taken(uow, email):
            raise exceptions.UserAlreadyExistsError(email=email)
        user = aggregate.User.register(
            email=email, full_name=input_dto.full_name, plaintext_password=input_dto.password
        )
        uow.repo(aggregate.User).add(user)
        uow.audit.add(
            audit.AuditEntry(
                actor=audit.Actor(id=None, label="self-registration"),
                action=value_objects.AuditAction.REGISTERED,
                aggregate_type=value_objects.AuditAggregateType.USER,
                aggregate_id=user.id.value,
            )
        )
    _LOGGER.info("User [%s] registered", user.id)
    return dto.UserOutputDTO.from_entity(user)


def login(*, uow: unit_of_work.UnitOfWork, input_dto: dto.LoginInputDTO) -> dto.TokenPairOutputDTO:
    with uow.transaction():
        email = value_objects.Email(value=input_dto.email)
        try:
            user = _user_repo(uow).get_by_email(email)
        except exceptions.UserNotFoundError as exc:
            # Deliberately the same error as a wrong password — don't leak whether an
            # email is registered.
            raise exceptions.InvalidCredentialsError() from exc
        if not user.is_active or not user.verify_password(input_dto.password):
            raise exceptions.InvalidCredentialsError()
        access_token = authentication.issue_access_token(user_id=str(user.id))
        refresh_token = refresh_tokens.issue(uow.session, user_id=user.id)
    _LOGGER.info("User [%s] logged in", user.id)
    return dto.TokenPairOutputDTO(access_token=access_token, refresh_token=refresh_token)


def refresh(
    *, uow: unit_of_work.UnitOfWork, input_dto: dto.RefreshInputDTO
) -> dto.TokenPairOutputDTO:
    with uow.transaction():
        user_id = refresh_tokens.redeem(uow.session, opaque_token=input_dto.refresh_token)
        user = uow.repo(aggregate.User).get(user_id)
        if not user.is_active:
            raise exceptions.UserNotActiveError(user_id=user.id)
        access_token = authentication.issue_access_token(user_id=str(user.id))
        new_refresh_token = refresh_tokens.issue(uow.session, user_id=user.id)
    return dto.TokenPairOutputDTO(access_token=access_token, refresh_token=new_refresh_token)


def deactivate_user(
    *, uow: unit_of_work.UnitOfWork, input_dto: dto.DeactivateUserInputDTO
) -> dto.UserOutputDTO:
    """Single-aggregate use case (ARCHITECTURE.md §10.1) — called directly from
    entrypoints/web/public.py, no orchestrator. `commerce/orders` reacts to this
    asynchronously via the outbox-published `UserDeactivated` event (§9.4/§10.3/§11) — do
    NOT add a second, synchronous call to another product's service here. An earlier draft
    of this template had a `orchestrators/deactivate_user_cascade.py` doing exactly that
    forwarding, unconditionally, to this one function — a Middle Man (§22.2) this codebase's
    own rule says to delete, not a real cross-product orchestration."""
    with uow.transaction():
        user_repo = uow.repo(aggregate.User)
        user_id = value_objects.UserId(value=input_dto.user_id)
        user = user_repo.get(user_id)
        user.deactivate()
        user_repo.update(user)
        refresh_tokens.revoke_all_for_user(uow.session, user_id=user.id)
        uow.audit.add(
            audit.AuditEntry(
                actor=audit.Actor(id=user.id.value, label=str(user.email)),
                action=value_objects.AuditAction.DEACTIVATED,
                aggregate_type=value_objects.AuditAggregateType.USER,
                aggregate_id=user.id.value,
            )
        )
    _LOGGER.info("User [%s] deactivated", user.id)
    return dto.UserOutputDTO.from_entity(user)


def expire_refresh_tokens(*, uow: unit_of_work.UnitOfWork) -> int:
    """Called only from entrypoints/cron/expire_refresh_tokens.py — kept as a services/
    function rather than letting the cron entrypoint touch adapters.refresh_tokens
    directly, same rule as every other entrypoint (ARCHITECTURE.md §9.5's cron jobs are
    still entrypoints, not an exception to 'entrypoints call services')."""
    with uow.transaction():
        return refresh_tokens.expire_stale(uow.session)


def get_user_profile(
    *, uow: unit_of_work.UnitOfWork, user_id: value_objects.UserId
) -> dto.UserProfileOutputDTO:
    """Called only from entrypoints/web/internal.py (§9.2) — service-to-service, never the
    customer JWT path."""
    with uow.transaction():
        user = uow.repo(aggregate.User).get(user_id)
    return dto.UserProfileOutputDTO.from_entity(user)


def _email_taken(uow: unit_of_work.UnitOfWork, email: value_objects.Email) -> bool:
    try:
        _user_repo(uow).get_by_email(email)
    except exceptions.UserNotFoundError:
        return False
    return True


def _user_repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultUserRepository:
    """`uow.repo(...)` returns the generic `Repository[T]` port, which deliberately has no
    `get_by_email` (bespoke queries stay off the generic interface, ARCHITECTURE.md §7).
    This cast is the one place that reaches for the concrete adapter's extra method —
    explicit and visible, not a silent `# type: ignore`."""
    return typing.cast(repository.DefaultUserRepository, uow.repo(aggregate.User))
