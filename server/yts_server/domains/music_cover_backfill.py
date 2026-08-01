from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..db.models import MusicCoverJob
from .cover_color import extract_theme_color
from .music_covers import FAILED, READY


async def backfill_music_cover_theme_colors(sessionmaker: async_sessionmaker) -> int:
    async with sessionmaker() as session:
        jobs = list(
            (
                await session.execute(
                    select(MusicCoverJob)
                    .where(
                        MusicCoverJob.status == READY,
                        MusicCoverJob.theme_color.is_(None),
                    )
                    .order_by(MusicCoverJob.created_at_ms.asc(), MusicCoverJob.id.asc())
                )
            ).scalars()
        )
        updated = 0
        for job in jobs:
            try:
                if not job.output_path:
                    raise RuntimeError("ready music cover is missing output_path")
                job.theme_color = extract_theme_color(Path(job.output_path).read_bytes())
                job.updated_at_ms = _now_ms()
                updated += 1
            except Exception as error:
                job.status = FAILED
                job.error_code = type(error).__name__[:64]
                job.error_message = str(error)
                job.finished_at_ms = _now_ms()
                job.updated_at_ms = _now_ms()
        await session.commit()
        return updated


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
