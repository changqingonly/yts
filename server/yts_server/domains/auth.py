from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from yts_core.config import get_settings

from ..db.models import UserAccount, UserSession
from ..errors import AppError
from ..security.password_keys import (
    issue_password_key,
    take_and_decrypt_password,
    take_and_decrypt_passwords,
)
from ..security.passwords import hash_password, verify_and_update_password
from ..security.refresh_tokens import (
    generate_refresh_token,
    hash_refresh_token,
    verify_refresh_token,
)
from ..security.tokens import decode_access_token, issue_access_token
from .credits import grant_daily_login_credit, grant_welcome_register_credit

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class AuthenticatedUser:
    session_id: str
    user_id: int
    user_uuid: str
    username: str
    email: str
    avatar_url: str | None
    expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    response: dict
    refresh_token: str
    device_id: str


def register_key_response() -> dict:
    issued = issue_password_key()
    return {"key_id": issued.key_id, "jwk": issued.jwk, "algorithm": "RSA-OAEP-256"}


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    key_id: str,
    password_ciphertext_b64: str,
    confirm_password_ciphertext_b64: str,
    agreement_accepted: bool,
    device_id: str,
    user_agent: str,
    ip_address: str,
) -> IssuedSession:
    email = _normalize_email(email)
    _validate_email(email)
    if not agreement_accepted:
        raise AppError.bad_request(
            "agreement_required", "must accept user agreement", "agreement_accepted"
        )
    if await _find_user_by_email(session, email) is not None:
        raise AppError.bad_request("registration_unavailable", "registration unavailable")
    password, confirm = take_and_decrypt_passwords(
        key_id, password_ciphertext_b64, confirm_password_ciphertext_b64
    )
    if password != confirm:
        raise AppError.bad_request(
            "password_mismatch", "passwords do not match", "confirm_password"
        )
    now = datetime.now(timezone.utc)
    user = UserAccount(
        id=_new_i64_id(),
        uuid=uuid.uuid4().hex,
        username=await _generate_unique_username(session, email),
        email=email,
        avatar_url=None,
        password_hash=hash_password(password),
        agreement_accepted=True,
    )
    session.add(user)
    await session.flush()
    await grant_welcome_register_credit(session, user.uuid, date.today())
    return await _issue_session(
        session, user, now, device_id=device_id, user_agent=user_agent, ip_address=ip_address
    )


async def login_user(
    session: AsyncSession,
    *,
    account: str,
    key_id: str,
    password_ciphertext_b64: str,
    device_id: str,
    user_agent: str,
    ip_address: str,
) -> IssuedSession:
    account = account.strip()
    if not account:
        raise AppError.bad_request("account_required", "account is required", "account")
    password = take_and_decrypt_password(key_id, password_ciphertext_b64)
    user = await _find_user_by_account(session, account)
    if user is None:
        # Keep Argon2 work on the unknown-account path comparable to a real login.
        hash_password(password)
        raise AppError.bad_request(
            "invalid_account_or_password", "invalid account or password", "account"
        )
    verified, replacement = verify_and_update_password(password, user.password_hash)
    if not verified:
        raise AppError.bad_request(
            "invalid_account_or_password", "invalid account or password", "account"
        )
    if replacement is not None:
        user.password_hash = replacement
    await grant_daily_login_credit(session, user.uuid, date.today())
    return await _issue_session(
        session,
        user,
        datetime.now(timezone.utc),
        device_id=device_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )


async def authenticate_bearer_token(
    session: AsyncSession, token: str, device_id: str
) -> AuthenticatedUser:
    settings = get_settings()
    claims = decode_access_token(settings=settings.auth, token=token)
    user_session = await session.get(UserSession, claims.sid)
    now = datetime.now(timezone.utc)
    if user_session is None or user_session.revoked_at is not None:
        raise AppError.unauthorized("session revoked")
    if (
        claims.sub != user_session.user_uuid
        or claims.uid != user_session.user_id
        or claims.did != user_session.device_id
        or device_id != user_session.device_id
    ):
        raise AppError.unauthorized("session identity mismatch")
    if (
        _as_utc_aware(user_session.expires_at) < now
        or _as_utc_aware(user_session.absolute_expires_at) < now
    ):
        raise AppError.unauthorized("session expired")
    user = await _find_user_by_uuid(session, claims.sub)
    if user is None or user.id != claims.uid:
        raise AppError.unauthorized("user not found")
    user_session.last_seen_at = now
    return AuthenticatedUser(
        user_session.id,
        user.id,
        user.uuid,
        user.username,
        user.email,
        user.avatar_url,
        user_session.expires_at,
    )


async def refresh_session(
    session: AsyncSession, *, refresh_token: str, device_id: str, request_id: str
) -> IssuedSession:
    if not refresh_token or not device_id or not request_id:
        raise AppError.unauthorized("missing refresh credentials")
    rows = (
        (
            await session.execute(
                select(UserSession).where(
                    UserSession.device_id == device_id, UserSession.revoked_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    matched = next(
        (row for row in rows if verify_refresh_token(refresh_token, row.refresh_token_hash)), None
    )
    if matched is None:
        previous = next(
            (
                row
                for row in rows
                if row.previous_refresh_token_hash
                and verify_refresh_token(refresh_token, row.previous_refresh_token_hash)
            ),
            None,
        )
        if previous is None or previous.last_refresh_request_id != request_id:
            if previous is not None:
                previous.revoked_at = datetime.now(timezone.utc)
                previous.revoke_reason = "refresh_replay"
                await session.commit()
            raise AppError.unauthorized("invalid refresh token")
        matched = previous
    now = datetime.now(timezone.utc)
    if _as_utc_aware(matched.expires_at) < now or _as_utc_aware(matched.absolute_expires_at) < now:
        matched.revoked_at = now
        matched.revoke_reason = "expired"
        await session.commit()
        raise AppError.unauthorized("session expired")
    user = await _find_user_by_uuid(session, matched.user_uuid)
    if user is None:
        raise AppError.unauthorized("user not found")
    new_refresh = generate_refresh_token()
    matched.previous_refresh_token_hash = matched.refresh_token_hash
    matched.refresh_token_hash = hash_refresh_token(new_refresh)
    matched.refresh_generation += 1
    matched.last_refresh_at = now
    matched.last_refresh_request_id = request_id
    matched.expires_at = min(
        now + timedelta(seconds=get_settings().auth.refresh_sliding_ttl_seconds),
        _as_utc_aware(matched.absolute_expires_at),
    )
    token = issue_access_token(
        settings=get_settings().auth,
        session_id=matched.id,
        user_id=user.id,
        user_uuid=user.uuid,
        device_id=device_id,
    )
    return IssuedSession(_auth_response(user, token), new_refresh, device_id)


async def logout(session: AsyncSession, session_id: str) -> None:
    user_session = await session.get(UserSession, session_id)
    if user_session is None:
        raise AppError.unauthorized("session not found")
    user_session.revoked_at = datetime.now(timezone.utc)
    user_session.revoke_reason = "logout"


async def _issue_session(
    session: AsyncSession,
    user: UserAccount,
    now: datetime,
    *,
    device_id: str,
    user_agent: str,
    ip_address: str,
) -> IssuedSession:
    settings = get_settings()
    session_id = uuid.uuid4().hex
    refresh = generate_refresh_token()
    absolute = now + timedelta(seconds=settings.auth.refresh_absolute_ttl_seconds)
    expires = min(now + timedelta(seconds=settings.auth.refresh_sliding_ttl_seconds), absolute)
    session.add(
        UserSession(
            id=session_id,
            user_id=user.id,
            user_uuid=user.uuid,
            device_id=device_id,
            refresh_token_hash=hash_refresh_token(refresh),
            previous_refresh_token_hash=None,
            refresh_generation=0,
            expires_at=expires,
            absolute_expires_at=absolute,
            last_seen_at=now,
            last_refresh_at=now,
            client_type="web",
            device_name="Web browser",
            app_version="",
            user_agent=user_agent[:512],
            ip_address=ip_address[:64],
        )
    )
    await session.flush()
    token = issue_access_token(
        settings=settings.auth,
        session_id=session_id,
        user_id=user.id,
        user_uuid=user.uuid,
        device_id=device_id,
    )
    return IssuedSession(_auth_response(user, token), refresh, device_id)


def _auth_response(user: UserAccount, token) -> dict:
    return {
        "uuid": user.uuid,
        "username": user.username,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "access_token": token.token,
        "token_type": "Bearer",
        "expires_at": int(token.expires_at.timestamp()),
        "offline_lease": "",
        "offline_lease_expires_at": 0,
    }


def _normalize_email(email: str) -> str:
    return email.strip().casefold()


def _validate_email(email: str) -> None:
    if not email:
        raise AppError.bad_request("email_required", "email is required", "email")
    if len(email) > 255 or not EMAIL_PATTERN.match(email):
        raise AppError.bad_request("email_invalid", "email is invalid", "email")


async def _generate_unique_username(session: AsyncSession, email: str) -> str:
    base = email.split("@", 1)[0]
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_") or "yts_user"
    for index in range(32):
        username = clean if index == 0 else f"{clean}_{index}"
        if await _find_user_by_username(session, username) is None:
            return username
    raise AppError.bad_request("username_unavailable", "failed to generate username")


async def _find_user_by_email(session: AsyncSession, email: str):
    return (
        await session.execute(select(UserAccount).where(UserAccount.email == email))
    ).scalar_one_or_none()


async def _find_user_by_username(session: AsyncSession, username: str):
    return (
        await session.execute(select(UserAccount).where(UserAccount.username == username))
    ).scalar_one_or_none()


async def _find_user_by_uuid(session: AsyncSession, user_uuid: str):
    return (
        await session.execute(select(UserAccount).where(UserAccount.uuid == user_uuid))
    ).scalar_one_or_none()


async def _find_user_by_account(session: AsyncSession, account: str):
    normalized = account.casefold() if "@" in account else account
    return (
        await session.execute(
            select(UserAccount).where(
                or_(UserAccount.email == normalized, UserAccount.username == account)
            )
        )
    ).scalar_one_or_none()


def _new_i64_id() -> int:
    return time.time_ns()


def _as_utc_aware(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
