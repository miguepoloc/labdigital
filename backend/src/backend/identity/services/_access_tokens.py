"""Emisión del access (sólo `identity` firma — commons.adapters.authentication)."""

from backend.commons.adapters import authentication
from backend.identity.users.services import dto as users_dto


def issue(*, claims: users_dto.TokenClaimsOutputDTO, session_id: str) -> str:
    return authentication.issue_access_token(
        user_id=claims.user_id,
        session_id=session_id,
        role=claims.role,
        credentials_version=claims.credentials_version,
        email=claims.email,
        name=claims.full_name,
    )
