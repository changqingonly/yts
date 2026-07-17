from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from yts_core.config import AuthSettings

from ..errors import AppError


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class AccessClaims:
    iss: str
    aud: str
    sub: str
    uid: int
    sid: str
    did: str
    iat: int
    nbf: int
    exp: int
    jti: str
    typ: str

    def as_payload(self) -> dict[str, str | int]:
        return self.__dict__.copy()


def issue_access_token(
    *,
    settings: AuthSettings,
    session_id: str,
    user_id: int,
    user_uuid: str,
    device_id: str,
) -> AccessToken:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.access_token_ttl_seconds)
    claims = AccessClaims(
        iss=settings.issuer,
        aud=settings.audience,
        sub=user_uuid,
        uid=user_id,
        sid=session_id,
        did=device_id,
        iat=int(now.timestamp()),
        nbf=int(now.timestamp()),
        exp=int(expires_at.timestamp()),
        jti=uuid.uuid4().hex,
        typ="access",
    )
    token = jwt.encode(
        claims.as_payload(),
        settings.jwt_secret_value,
        algorithm="HS256",
        headers={"kid": settings.jwt_active_kid},
    )
    return AccessToken(token=token, expires_at=expires_at)


def decode_access_token(*, settings: AuthSettings, token: str) -> AccessClaims:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("kid") != settings.jwt_active_kid:
            raise jwt.InvalidKeyError("unknown signing key")
        payload = jwt.decode(
            token,
            settings.jwt_secret_value,
            algorithms=["HS256"],
            issuer=settings.issuer,
            audience=settings.audience,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "uid",
                    "sid",
                    "did",
                    "iat",
                    "nbf",
                    "exp",
                    "jti",
                    "typ",
                ]
            },
        )
        claims = AccessClaims(**payload)
        if claims.typ != "access":
            raise jwt.InvalidTokenError("wrong token type")
    except (jwt.PyJWTError, TypeError, ValueError) as exc:
        raise AppError.unauthorized("invalid access token") from exc
    return claims
