from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Cookie, Header, Request, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..domains import auth as auth_domain
from ..errors import AppError
from ..security.rate_limits import auth_limiter
from .dependencies import CurrentUser, DbSession

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    key_id: str
    password_ciphertext_b64: str
    confirm_password_ciphertext_b64: str
    agreement_accepted: bool


class LoginRequest(BaseModel):
    account: str
    key_id: str
    password_ciphertext_b64: str


@router.get("/register_key")
async def register_key(request: Request) -> dict:
    auth_limiter.check("password-key", _client_ip(request), limit=60, window_seconds=60)
    return auth_domain.register_key_response()


@router.get("/login_key")
async def login_key(request: Request) -> dict:
    auth_limiter.check("password-key", _client_ip(request), limit=60, window_seconds=60)
    return auth_domain.register_key_response()


@router.get("/register_check")
async def register_check(request: Request, session: DbSession, email: str = "") -> dict:
    auth_limiter.check("register-check", _client_ip(request), limit=60, window_seconds=300)
    return {"email_ok": True, "email_msg": ""}


@router.post("/register")
async def register(
    req: RegisterRequest,
    session: DbSession,
    request: Request,
    response: Response,
    device_id: str | None = Cookie(default=None, alias="yts-device"),
) -> dict:
    auth_limiter.check("register", _client_ip(request), limit=50, window_seconds=300)
    issued = await auth_domain.register_user(
        session,
        email=req.email,
        key_id=req.key_id,
        password_ciphertext_b64=req.password_ciphertext_b64,
        confirm_password_ciphertext_b64=req.confirm_password_ciphertext_b64,
        agreement_accepted=req.agreement_accepted,
        device_id=device_id or uuid.uuid4().hex,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError.bad_request("registration_unavailable", "registration unavailable") from exc
    _set_session_cookies(response, issued)
    return issued.response


@router.post("/login")
async def login(
    req: LoginRequest,
    session: DbSession,
    request: Request,
    response: Response,
    device_id: str | None = Cookie(default=None, alias="yts-device"),
) -> dict:
    key = f"{_client_ip(request)}:{hashlib.sha256(req.account.strip().casefold().encode()).hexdigest()}"
    auth_limiter.check("login", key, limit=10, window_seconds=300)
    issued = await auth_domain.login_user(
        session,
        account=req.account,
        key_id=req.key_id,
        password_ciphertext_b64=req.password_ciphertext_b64,
        device_id=device_id or uuid.uuid4().hex,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    await session.commit()
    _set_session_cookies(response, issued)
    return issued.response


@router.post("/refresh")
async def refresh(
    response: Response,
    session: DbSession,
    refresh_token: str | None = Cookie(default=None, alias="yts-refresh"),
    device_id: str | None = Cookie(default=None, alias="yts-device"),
    request_id: str | None = Header(default=None, alias="X-Refresh-Request-ID"),
) -> dict:
    auth_limiter.check("refresh", device_id or "missing", limit=20, window_seconds=60)
    issued = await auth_domain.refresh_session(
        session,
        refresh_token=refresh_token or "",
        device_id=device_id or "",
        request_id=request_id or "",
    )
    await session.commit()
    _set_session_cookies(response, issued)
    return issued.response


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return {
        "uuid": user.user_uuid,
        "user_uuid": user.user_uuid,
        "username": user.username,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "offline_lease": "",
        "offline_lease_expires_at": 0,
    }


@router.post("/logout")
async def logout(
    user: CurrentUser,
    session: DbSession,
    response: Response,
) -> dict:
    await auth_domain.logout(session, user.session_id)
    await session.commit()
    response.delete_cookie("yts-refresh", path="/api/auth")
    response.delete_cookie("yts-device", path="/")
    return {"ok": True}


def _set_session_cookies(response: Response, issued: auth_domain.IssuedSession) -> None:
    from yts_core.config import get_settings

    settings = get_settings().auth
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(
        "yts-device",
        issued.device_id,
        path="/",
        max_age=settings.refresh_absolute_ttl_seconds,
        **common,
    )
    response.set_cookie(
        "yts-refresh",
        issued.refresh_token,
        path="/api/auth",
        max_age=settings.refresh_sliding_ttl_seconds,
        **common,
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
