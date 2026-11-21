"""Capa de aplicación de `identity.sessions`: emisión, rotación con detección de reuso y
revocación de familias de refresh tokens."""

import typing
import uuid

from backend.commons.adapters import logs, unit_of_work
from backend.commons.domain import audit
from backend.commons.domain import value_objects as base_value_objects
from backend.identity.commons import value_objects as identity_value_objects
from backend.identity.sessions.adapters import repository
from backend.identity.sessions.domain.model import aggregate, exceptions, value_objects
from backend.identity.sessions.services import dto

_LOGGER = logs.get_logger()


def start_session(
    *, uow: unit_of_work.UnitOfWork, input_dto: dto.StartSessionInputDTO
) -> dto.IssuedRefreshOutputDTO:
    with uow.transaction():
        session, opaque = aggregate.Session.start(
            user_id=_user_id(input_dto.user_id),
            credentials_version=input_dto.credentials_version,
            persistent=input_dto.persistent,
            user_agent=input_dto.user_agent,
            ip=input_dto.ip,
        )
        uow.repo(aggregate.Session).add(session)
    return _issued(session, opaque)


def rotate(
    *, uow: unit_of_work.UnitOfWork, refresh_token: str, ip: str, user_agent: str
) -> dto.IssuedRefreshOutputDTO:
    """Canjea un refresh. Reuso ⇒ la familia queda revocada y auditada (se CONFIRMA) y
    después se lanza `RefreshTokenInvalidError`. No llamar dentro de una transacción
    exterior: el rollback desharía la revocación."""
    opaque = value_objects.OpaqueRefreshToken.parse(refresh_token)
    if opaque is None:
        raise exceptions.RefreshTokenInvalidError()

    with uow.transaction():
        repo = _repo(uow)
        found = repo.find_by_token_id(opaque.token_id)
        if found is None:
            raise exceptions.RefreshTokenInvalidError()
        session, presented = found
        redemption = session.redeem(
            presented=presented, secret=opaque.secret, ip=ip, user_agent=user_agent
        )
        match redemption.outcome:
            case value_objects.RedeemOutcome.ROTATED:
                repo.update(session)
            case value_objects.RedeemOutcome.REUSED:
                repo.update(session)
                uow.audit.add(
                    audit.AuditEntry(
                        actor=audit.Actor(id=None, label=f"ip:{ip}"),
                        action=value_objects.AuditAction.REFRESH_REUSE_DETECTED.value,
                        aggregate_type=value_objects.AuditAggregateType.SESSION.value,
                        aggregate_id=str(session.id),
                        changes={
                            "user_id": str(session.user_id),
                            "token_id": str(presented.id),
                            "ip": ip,
                            "user_agent": user_agent[:200],
                        },
                    )
                )
            case value_objects.RedeemOutcome.INVALID:
                pass

    if redemption.outcome is value_objects.RedeemOutcome.REUSED:
        _LOGGER.warning("Reuso de refresh detectado; sesión [%s] revocada", session.id)
    if redemption.new_token is None:
        raise exceptions.RefreshTokenInvalidError()
    return _issued(session, redemption.new_token)


def revoke_by_refresh_token(
    *, uow: unit_of_work.UnitOfWork, refresh_token: str, reason: value_objects.RevokeReason
) -> str | None:
    """Logout con la cookie de refresh: revoca su sesión si el secreto es correcto (sea el
    vigente o uno rotado). Devuelve el id de la sesión revocada o `None`. Nunca falla."""
    opaque = value_objects.OpaqueRefreshToken.parse(refresh_token)
    if opaque is None:
        return None
    with uow.transaction():
        repo = _repo(uow)
        found = repo.find_by_token_id(opaque.token_id)
        if found is None:
            return None
        session, presented = found
        if presented.token_hash != value_objects.hash_secret(opaque.secret):
            return None
        if session.revoke(reason):
            repo.update(session)
    return str(session.id)


def revoke_session(
    *,
    uow: unit_of_work.UnitOfWork,
    session_id: str,
    owner_user_id: str,
    reason: value_objects.RevokeReason,
) -> None:
    """Cierra una sesión del propio usuario; la de otro usuario se ve como inexistente."""
    with uow.transaction():
        repo = _repo(uow)
        session = repo.get(_session_id(session_id))
        if str(session.user_id) != owner_user_id:
            raise exceptions.SessionNotFoundError()
        if session.revoke(reason):
            repo.update(session)


def revoke_all_for_user(
    *,
    uow: unit_of_work.UnitOfWork,
    user_id: str,
    reason: value_objects.RevokeReason,
    keep_session_id: str | None = None,
) -> int:
    """Revoca todas las sesiones activas del usuario salvo `keep_session_id`."""
    revoked = 0
    with uow.transaction():
        repo = _repo(uow)
        for session in repo.list_active_for_user(_user_id(user_id)):
            if str(session.id) == keep_session_id:
                continue
            if session.revoke(reason):
                repo.update(session)
                revoked += 1
    return revoked


def sync_credentials_version(
    *, uow: unit_of_work.UnitOfWork, session_id: str, credentials_version: int
) -> None:
    with uow.transaction():
        repo = _repo(uow)
        session = repo.get(_session_id(session_id))
        session.sync_credentials_version(credentials_version)
        repo.update(session)


def ensure_active(*, uow: unit_of_work.UnitOfWork, session_id: str, user_id: str) -> None:
    """Para operaciones sensibles con el access en mano (p. ej. cambio de contraseña):
    confirma que su sesión sigue viva en BD."""
    with uow.transaction():
        try:
            session = _repo(uow).get(_session_id(session_id))
        except exceptions.SessionNotFoundError as exc:
            raise exceptions.RefreshTokenInvalidError() from exc
        if str(session.user_id) != user_id or not session.is_active():
            raise exceptions.RefreshTokenInvalidError()


def list_active(
    *, uow: unit_of_work.UnitOfWork, user_id: str, current_session_id: str | None
) -> list[dto.SessionOutputDTO]:
    with uow.transaction():
        sessions = _repo(uow).list_active_for_user(_user_id(user_id))
    return [
        dto.SessionOutputDTO.from_entity(s, current_session_id=current_session_id) for s in sessions
    ]


def delete_expired(*, uow: unit_of_work.UnitOfWork) -> int:
    """Housekeeping (worker): borra familias caducadas/revocadas hace más de 7 días."""
    cutoff = base_value_objects.PosixTime(
        microseconds=base_value_objects.PosixTime.now().microseconds - 7 * 86_400 * 1_000_000
    )
    with uow.transaction():
        return _repo(uow).delete_expired(older_than=cutoff)


def _issued(
    session: aggregate.Session, opaque: value_objects.OpaqueRefreshToken
) -> dto.IssuedRefreshOutputDTO:
    return dto.IssuedRefreshOutputDTO(
        session_id=str(session.id),
        user_id=str(session.user_id),
        credentials_version=session.credentials_version,
        refresh_token=str(opaque),
        persistent=session.persistent,
        refresh_expires_at_microseconds=session.refresh_expires_at().microseconds,
    )


def _user_id(raw: str) -> identity_value_objects.UserId:
    return identity_value_objects.UserId(value=uuid.UUID(raw))


def _session_id(raw: str) -> value_objects.SessionId:
    try:
        return value_objects.SessionId(value=uuid.UUID(raw))
    except ValueError as exc:
        raise exceptions.SessionNotFoundError() from exc


def _repo(uow: unit_of_work.UnitOfWork) -> repository.DefaultSessionRepository:
    return typing.cast(repository.DefaultSessionRepository, uow.repo(aggregate.Session))
