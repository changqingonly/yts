from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_sessionmaker
from ..domains.auth import AuthenticatedUser, authenticate_bearer_token
from ..errors import AppError


async def db_session() -> AsyncIterator[AsyncSession]:
    maker = get_sessionmaker()
    async with maker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(db_session)]


async def current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError.unauthorized("missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError.unauthorized("missing bearer token")
    return await authenticate_bearer_token(session, token)


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]
