from __future__ import annotations

import asyncio

from .db.bootstrap import create_all_tables
from .db.session import get_sessionmaker
from .domains.music_cover_backfill import backfill_music_cover_theme_colors


async def _run() -> int:
    await create_all_tables()
    return await backfill_music_cover_theme_colors(get_sessionmaker())


def main() -> int:
    updated = asyncio.run(_run())
    print(f"music cover theme colors updated: {updated}")
    return 0
