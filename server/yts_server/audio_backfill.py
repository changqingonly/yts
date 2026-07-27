from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db.bootstrap import create_all_tables
from .db.models import AudioPlaybackRendition, LocalImportBlob
from .db.session import get_sessionmaker
from .domains.audio_renditions import (
    FAILED,
    PLAYBACK_PROFILE,
    READY,
    ensure_pending_rendition,
    process_next_pending_rendition,
)


async def backfill_audio_renditions(
    sessionmaker: async_sessionmaker,
    *,
    ffmpeg_executable: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, int]:
    async with sessionmaker() as session:
        content_hashes = list(
            (
                await session.execute(
                    select(LocalImportBlob.hash).order_by(LocalImportBlob.hash.asc())
                )
            ).scalars()
        )
        existing_hashes = set(
            (
                await session.execute(
                    select(AudioPlaybackRendition.original_content_hash).where(
                        AudioPlaybackRendition.profile == PLAYBACK_PROFILE
                    )
                )
            ).scalars()
        )
        created = 0
        for content_hash in content_hashes:
            if content_hash in existing_hashes:
                continue
            await ensure_pending_rendition(session, content_hash)
            created += 1
        await session.commit()

    while await process_next_pending_rendition(
        sessionmaker,
        ffmpeg_executable=ffmpeg_executable,
        output_dir=output_dir,
    ):
        pass

    async with sessionmaker() as session:
        counts = dict(
            (
                await session.execute(
                    select(AudioPlaybackRendition.status, func.count())
                    .where(AudioPlaybackRendition.profile == PLAYBACK_PROFILE)
                    .group_by(AudioPlaybackRendition.status)
                )
            ).all()
        )
    return {
        "total": len(content_hashes),
        "created": created,
        "skipped": len(content_hashes) - created,
        "ready": int(counts.get(READY, 0)),
        "failed": int(counts.get(FAILED, 0)),
    }


async def _run() -> dict[str, int]:
    await create_all_tables()
    return await backfill_audio_renditions(get_sessionmaker())


def main() -> int:
    summary = asyncio.run(_run())
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 1 if summary["failed"] else 0
