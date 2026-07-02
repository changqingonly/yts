from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest


@pytest.fixture(autouse=True)
def reset_cached_settings(monkeypatch: pytest.MonkeyPatch):
    from yts_core.config import get_settings

    monkeypatch.delenv("YTS_CONFIG_FILE", raising=False)
    monkeypatch.delenv("YTS_CONFIG_HOME", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def reset_cached_db_engine() -> None:
    from yts_server.db.session import get_engine, get_sessionmaker

    if get_engine.cache_info().currsize:
        engine = get_engine()
        with suppress(Exception):
            asyncio.run(engine.dispose())
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
