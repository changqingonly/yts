from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Cookie, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from yts_core.config import Profile, get_settings

from ..db.session import get_sessionmaker
from ..domains.auth import AuthenticatedUser, authenticate_bearer_token, ensure_local_user
from ..errors import AppError


async def db_session() -> AsyncIterator[AsyncSession]:
    maker = get_sessionmaker()
    async with maker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(db_session)]


async def current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    device_id_cookie: Annotated[str | None, Cookie(alias="yts-device")] = None,
    device_id_header: Annotated[str | None, Header(alias="X-Yts-Device-Id")] = None,
) -> AuthenticatedUser:
    # 打包态(Tauri webview)跨源 cookie 不可靠(见 routes/auth.py 的 /refresh body 兜底同款问题),
    # 除了 yts-device cookie 外,也接受显式 X-Yts-Device-Id 头,cookie 优先。
    device_id = device_id_cookie or device_id_header
    settings = get_settings()
    if settings.profile != Profile.CLOUD:
        # 账号体系只走云端;本地(单机单用户)业务接口不要求真实会话,统一落到
        # 一个固定的本地隐式账号,避免云端签发的 session 在本地库里找不到对应行而 401。
        user = await ensure_local_user(session)
        return AuthenticatedUser(
            session_id="local",
            user_id=user.id,
            user_uuid=user.uuid,
            username=user.username,
            email=user.email,
            avatar_url=user.avatar_url,
            expires_at=datetime(9999, 12, 31, tzinfo=timezone.utc),
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError.unauthorized("missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError.unauthorized("missing bearer token")
    if not device_id:
        raise AppError.unauthorized("missing device credential")
    return await authenticate_bearer_token(session, token, device_id)


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]
