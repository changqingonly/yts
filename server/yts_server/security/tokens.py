from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from ..errors import AppError


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: datetime


def issue_access_token(
    *,
    secret: str,
    session_id: int,
    user_id: int,
    user_uuid: str,
    ttl_seconds: int,
) -> AccessToken:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    token = jwt.encode(
        {
            "sid": session_id,
            "uid": user_id,
            "sub": user_uuid,
            "exp": int(expires_at.timestamp()),
        },
        secret,
        algorithm="HS256",
    )
    return AccessToken(token=token, expires_at=expires_at)


def decode_access_token(*, secret: str, token: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError.unauthorized("invalid access token") from exc
    return payload
