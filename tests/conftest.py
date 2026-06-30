from __future__ import annotations

import asyncio
from contextlib import suppress


def reset_cached_db_engine() -> None:
    from yts_server.db.session import get_engine, get_sessionmaker

    if get_engine.cache_info().currsize:
        engine = get_engine()
        with suppress(Exception):
            asyncio.run(engine.dispose())
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
