from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DailyUsageCounter
from ..errors import AppError

SCENE_LIMITS = {
    "lyrics": 100,
    "images": 100,
    "audio_effects": 100,
}


@dataclass(frozen=True)
class UsageState:
    scene: str
    used: int
    limit: int


async def get_daily_usage(session: AsyncSession, user_uuid: str, usage_date: date) -> dict:
    return {
        scene: _usage_response(await _counter(session, user_uuid, scene, usage_date))
        for scene in SCENE_LIMITS
    }


async def admit_usage(
    session: AsyncSession, *, user_uuid: str, scene: str, usage_date: date
) -> UsageState:
    counter = await _counter(session, user_uuid, scene, usage_date)
    if counter.used >= counter.limit:
        raise AppError.quota_exhausted(scene)
    counter.used += 1
    await session.flush()
    return UsageState(scene=scene, used=counter.used, limit=counter.limit)


async def assert_usage_available(
    session: AsyncSession, *, user_uuid: str, scene: str, usage_date: date
) -> UsageState:
    counter = await _counter(session, user_uuid, scene, usage_date)
    if counter.used >= counter.limit:
        raise AppError.quota_exhausted(scene)
    return UsageState(scene=scene, used=counter.used, limit=counter.limit)


async def _counter(
    session: AsyncSession, user_uuid: str, scene: str, usage_date: date
) -> DailyUsageCounter:
    if scene not in SCENE_LIMITS:
        raise AppError.bad_request("unknown_usage_scene", f"unknown usage scene: {scene}", "scene")
    statement = select(DailyUsageCounter).where(
        DailyUsageCounter.user_uuid == user_uuid,
        DailyUsageCounter.scene == scene,
        DailyUsageCounter.usage_date == usage_date,
    )
    counter = (await session.execute(statement)).scalar_one_or_none()
    if counter is None:
        counter = DailyUsageCounter(
            id=_new_i64_id(),
            user_uuid=user_uuid,
            scene=scene,
            usage_date=usage_date,
            used=0,
            limit=SCENE_LIMITS[scene],
        )
        session.add(counter)
        await session.flush()
    return counter


def _usage_response(counter: DailyUsageCounter) -> dict:
    return {"used": counter.used, "limit": counter.limit, "remaining": counter.limit - counter.used}


def _new_i64_id() -> int:
    return time.time_ns()
