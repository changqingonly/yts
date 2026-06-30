from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

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
from ..security.passwords import hash_password, verify_password
from ..security.tokens import decode_access_token, issue_access_token
from .credits import grant_daily_login_credit, grant_welcome_register_credit

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class AuthenticatedUser:
    session_id: int
    user_id: int
    user_uuid: str
    username: str
    email: str
    avatar_url: str | None
    expires_at: datetime


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
) -> dict:
    email = email.strip()
    _validate_email(email)
    if not agreement_accepted:
        raise AppError.bad_request(
            "agreement_required", "must accept user agreement", "agreement_accepted"
        )
    if await _find_user_by_email(session, email) is not None:
        raise AppError.bad_request("email_exists", "email already exists", "email")
    password, confirm = take_and_decrypt_passwords(
        key_id, password_ciphertext_b64, confirm_password_ciphertext_b64
    )
    if password != confirm:
        raise AppError.bad_request("password_mismatch", "passwords do not match", "confirm_password")
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
    token = await _issue_session_token(session, user, now)
    return _auth_response(user, token)


async def login_user(
    session: AsyncSession,
    *,
    account: str,
    key_id: str,
    password_ciphertext_b64: str,
) -> dict:
    account = account.strip()
    if not account:
        raise AppError.bad_request("account_required", "account is required", "account")
    password = take_and_decrypt_password(key_id, password_ciphertext_b64)
    user = await _find_user_by_account(session, account)
    if user is None or not verify_password(password, user.password_hash):
        raise AppError.bad_request("invalid_account_or_password", "invalid account or password", "account")
    await grant_daily_login_credit(session, user.uuid, date.today())
    token = await _issue_session_token(session, user, datetime.now(timezone.utc))
    return _auth_response(user, token)


async def authenticate_bearer_token(session: AsyncSession, token: str) -> AuthenticatedUser:
    settings = get_settings()
    payload = decode_access_token(secret=settings.auth_jwt_secret, token=token)
    session_id = int(payload.get("sid") or 0)
    user_uuid = str(payload.get("sub") or "")
    if not session_id or not user_uuid:
        raise AppError.unauthorized("invalid access token")
    user_session = await session.get(UserSession, session_id)
    if user_session is None or user_session.revoked_at is not None:
        raise AppError.unauthorized("session revoked")
    if _as_utc_aware(user_session.expires_at) < datetime.now(timezone.utc):
        raise AppError.unauthorized("session expired")
    user = await _find_user_by_uuid(session, user_uuid)
    if user is None:
        raise AppError.unauthorized("user not found")
    return AuthenticatedUser(
        session_id=session_id,
        user_id=user.id,
        user_uuid=user.uuid,
        username=user.username,
        email=user.email,
        avatar_url=user.avatar_url,
        expires_at=user_session.expires_at,
    )


async def logout(session: AsyncSession, session_id: int) -> None:
    user_session = await session.get(UserSession, session_id)
    if user_session is None:
        raise AppError.unauthorized("session not found")
    user_session.revoked_at = datetime.now(timezone.utc)


async def _issue_session_token(session: AsyncSession, user: UserAccount, now: datetime):
    settings = get_settings()
    session_id = _new_i64_id()
    issued = issue_access_token(
        secret=settings.auth_jwt_secret,
        session_id=session_id,
        user_id=user.id,
        user_uuid=user.uuid,
        ttl_seconds=settings.auth_access_token_ttl_seconds,
    )
    session.add(UserSession(id=session_id, user_uuid=user.uuid, expires_at=issued.expires_at))
    await session.flush()
    return issued


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


async def _generate_unique_username(session: AsyncSession, email: str) -> str:
    base = email.split("@", 1)[0]
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_") or "yts_user"
    for index in range(32):
        username = clean if index == 0 else f"{clean}_{index}"
        if await _find_user_by_username(session, username) is None:
            return username
    raise AppError.bad_request("username_unavailable", "failed to generate username")


def _validate_email(email: str) -> None:
    if not email:
        raise AppError.bad_request("email_required", "email is required", "email")
    if len(email) > 255 or not EMAIL_PATTERN.match(email):
        raise AppError.bad_request("email_invalid", "email is invalid", "email")


async def _find_user_by_email(session: AsyncSession, email: str) -> UserAccount | None:
    return (
        await session.execute(select(UserAccount).where(UserAccount.email == email))
    ).scalar_one_or_none()


async def _find_user_by_username(session: AsyncSession, username: str) -> UserAccount | None:
    return (
        await session.execute(select(UserAccount).where(UserAccount.username == username))
    ).scalar_one_or_none()


async def _find_user_by_uuid(session: AsyncSession, user_uuid: str) -> UserAccount | None:
    return (
        await session.execute(select(UserAccount).where(UserAccount.uuid == user_uuid))
    ).scalar_one_or_none()


async def _find_user_by_account(session: AsyncSession, account: str) -> UserAccount | None:
    return (
        await session.execute(
            select(UserAccount).where(
                or_(UserAccount.email == account, UserAccount.username == account)
            )
        )
    ).scalar_one_or_none()


def _new_i64_id() -> int:
    return time.time_ns()


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
