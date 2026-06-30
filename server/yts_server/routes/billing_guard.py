from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from yts_core.config import Profile, get_settings

from ..domains import credits as credits_domain
from ..domains import usage as usage_domain
from ..domains.auth import AuthenticatedUser, authenticate_bearer_token
from ..errors import AppError


async def billing_user_if_required(
    session: AsyncSession, authorization: str | None
) -> AuthenticatedUser | None:
    settings = get_settings()
    if settings.profile != Profile.CLOUD or not settings.billing_enabled:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError.unauthorized("missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError.unauthorized("missing bearer token")
    return await authenticate_bearer_token(session, token)


class GenerationBillingGuard:
    def __init__(
        self,
        *,
        session: AsyncSession,
        user: AuthenticatedUser | None,
        request_id: str,
        credit_scene: str,
        usage_scene: str | None,
    ) -> None:
        self._session = session
        self._user = user
        self._request_id = request_id
        self._credit_scene = credit_scene
        self._usage_scene = usage_scene
        self._reservation_key = ""

    async def __aenter__(self) -> None:
        if self._user is None:
            return
        if self._usage_scene:
            await usage_domain.assert_usage_available(
                self._session,
                user_uuid=self._user.user_uuid,
                scene=self._usage_scene,
                usage_date=date.today(),
            )
        reservation = await credits_domain.reserve_generation_credit(
            self._session,
            user_uuid=self._user.user_uuid,
            request_id=self._request_id,
            scene=self._credit_scene,
        )
        if self._usage_scene:
            await usage_domain.admit_usage(
                self._session,
                user_uuid=self._user.user_uuid,
                scene=self._usage_scene,
                usage_date=date.today(),
            )
        await self._session.commit()
        self._reservation_key = reservation.reservation_key

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._user is None or not self._reservation_key:
            return False
        if exc is None:
            await credits_domain.capture_generation_credit(
                self._session,
                reservation_key=self._reservation_key,
                idempotency_key=f"{self._reservation_key}:capture",
            )
        else:
            await credits_domain.release_generation_credit(
                self._session,
                reservation_key=self._reservation_key,
                idempotency_key=f"{self._reservation_key}:release",
            )
        await self._session.commit()
        return False
