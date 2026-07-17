from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import jwt
import pytest
from yts_core.config import AuthSettings
from yts_server.errors import AppError
from yts_server.security.passwords import hash_password, verify_and_update_password
from yts_server.security.refresh_tokens import (
    generate_refresh_token,
    hash_refresh_token,
    verify_refresh_token,
)
from yts_server.security.tokens import AccessClaims, decode_access_token, issue_access_token


def auth_settings() -> AuthSettings:
    return AuthSettings(jwt_secret="test-signing-secret-that-is-long-enough-for-hs256")


def test_password_verification_returns_rehash_when_parameters_change() -> None:
    digest = hash_password("Password123")

    verified, replacement = verify_and_update_password("Password123", digest, time_cost=4)

    assert verified is True
    assert replacement is not None
    assert replacement != digest


def test_refresh_token_is_random_and_verified_by_digest() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()
    digest = hash_refresh_token(first)

    assert first != second
    assert first not in digest
    assert verify_refresh_token(first, digest)
    assert not verify_refresh_token(second, digest)


def test_access_token_requires_complete_claim_contract() -> None:
    settings = auth_settings()
    issued = issue_access_token(
        settings=settings,
        session_id="session-1",
        user_id=7,
        user_uuid="user-1",
        device_id="device-1",
    )

    claims = decode_access_token(settings=settings, token=issued.token)

    assert claims.sid == "session-1"
    assert claims.uid == 7
    assert claims.sub == "user-1"
    assert claims.did == "device-1"
    assert claims.typ == "access"
    assert claims.jti
    assert jwt.get_unverified_header(issued.token)["kid"] == settings.jwt_active_kid


def test_access_token_rejects_wrong_audience_and_type() -> None:
    settings = auth_settings()
    issued = issue_access_token(
        settings=settings,
        session_id="session-1",
        user_id=7,
        user_uuid="user-1",
        device_id="device-1",
    )
    claims = decode_access_token(settings=settings, token=issued.token)
    payload = claims.as_payload()
    payload["aud"] = "other-client"
    wrong_audience = jwt.encode(
        payload,
        settings.jwt_secret_value,
        algorithm="HS256",
        headers={"kid": settings.jwt_active_kid},
    )

    with pytest.raises(AppError):
        decode_access_token(settings=settings, token=wrong_audience)

    wrong_type = replace(claims, typ="refresh")
    token = jwt.encode(
        wrong_type.as_payload(),
        settings.jwt_secret_value,
        algorithm="HS256",
        headers={"kid": settings.jwt_active_kid},
    )
    with pytest.raises(AppError):
        decode_access_token(settings=settings, token=token)


def test_access_token_rejects_missing_required_claim() -> None:
    settings = auth_settings()
    now = int(datetime.now(timezone.utc).timestamp())
    payload = AccessClaims(
        iss=settings.issuer,
        aud=settings.audience,
        sub="user-1",
        uid=7,
        sid="session-1",
        did="device-1",
        iat=now,
        nbf=now,
        exp=now + 60,
        jti="token-1",
        typ="access",
    ).as_payload()
    del payload["did"]
    token = jwt.encode(
        payload,
        settings.jwt_secret_value,
        algorithm="HS256",
        headers={"kid": settings.jwt_active_kid},
    )

    with pytest.raises(AppError):
        decode_access_token(settings=settings, token=token)
