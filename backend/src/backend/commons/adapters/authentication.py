"""JWT RS256 de acceso — ARCHITECTURE.md §9.3, contrato §2.

Sólo `identity` firma (tiene la clave privada); cualquier contexto (y nginx vía
`/auth/verify`, y los módulos vía JWKS) verifica localmente con la clave pública, sin BD.

Claims: `iss="labdigital"`, `aud="labdigital"`, `sub` (UUIDv7 del usuario), `sid` (sesión),
`role`, `ver` (versión de credenciales), `email`, `name`, `iat`, `exp`, `jti`; cabecera `kid`.
"""

import datetime
import functools
from typing import Any
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from jwt import algorithms
import pydantic

from backend.commons.adapters import settings

ALGORITHM = "RS256"
ISSUER = "labdigital"
AUDIENCE = "labdigital"
ACCESS_TOKEN_TTL = datetime.timedelta(minutes=15)
_LEEWAY_SECONDS = 10


class AccessClaims(pydantic.BaseModel):
    """Lo que un access válido garantiza. Construido sólo por `verify_access_token`."""

    model_config = {"frozen": True}

    user_id: str
    session_id: str
    role: str
    credentials_version: int
    email: str
    name: str
    token_id: str


class InvalidAccessTokenError(Exception):
    """El access falta, está mal formado, caducó o no lo firmamos nosotros. La capa web lo
    traduce a 401 `token_invalid`; nunca dice cuál de esas causas fue."""


def issue_access_token(
    *,
    user_id: str,
    session_id: str,
    role: str,
    credentials_version: int,
    email: str,
    name: str,
) -> str:
    """Llamado sólo desde `identity` (único poseedor de la clave privada)."""
    app_settings = settings.get_settings()
    now = datetime.datetime.now(tz=datetime.UTC)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": user_id,
        "sid": session_id,
        "role": role,
        "ver": credentials_version,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        app_settings.jwt_private_key_pem,
        algorithm=ALGORITHM,
        headers={"kid": app_settings.jwt_kid},
    )


def verify_access_token(token: str) -> AccessClaims:
    """Valida firma, `kid`, `iss`, `aud`, `exp` y la presencia de todos los claims."""
    try:
        header = jwt.get_unverified_header(token)
        key = _public_keys_by_kid().get(str(header.get("kid", "")))
        if key is None:
            raise InvalidAccessTokenError("kid desconocido")
        payload = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub", "sid", "jti", "iss", "aud"]},
        )
        return AccessClaims(
            user_id=str(payload["sub"]),
            session_id=str(payload["sid"]),
            role=str(payload["role"]),
            credentials_version=int(payload["ver"]),
            email=str(payload["email"]),
            name=str(payload["name"]),
            token_id=str(payload["jti"]),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError(str(exc)) from exc


def jwks() -> dict[str, list[dict[str, Any]]]:
    """Documento JWKS público (`/.well-known/jwks.json`): clave vigente y, si existe, la
    anterior (rotación)."""
    keys: list[dict[str, Any]] = []
    for kid, public_key in _public_keys_by_kid().items():
        jwk = algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
        jwk.update({"kid": kid, "use": "sig", "alg": ALGORITHM})
        keys.append(jwk)
    return {"keys": keys}


def _public_keys_by_kid() -> dict[str, rsa.RSAPublicKey]:
    app_settings = settings.get_settings()
    keys = {app_settings.jwt_kid: _load_public_key(app_settings.jwt_public_key_pem)}
    if app_settings.jwt_previous_kid and app_settings.jwt_previous_public_key_pem:
        keys[app_settings.jwt_previous_kid] = _load_public_key(
            app_settings.jwt_previous_public_key_pem
        )
    return keys


@functools.lru_cache(maxsize=8)
def _load_public_key(pem: str) -> rsa.RSAPublicKey:
    key = serialization.load_pem_public_key(pem.encode())
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("JWT_PUBLIC_KEY_PEM no es una clave pública RSA.")
    return key
