from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path

import pytest

_COLLECTION_CONFIG = None
_ORIGINAL_YTS_ENV: dict[str, str] = {}


def _write_test_cloud_config(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    database_path = config_dir / "test.db"
    (config_dir / "cloud.env").write_text(
        "\n".join(
            [
                "YTS_PROFILE=cloud",
                f"YTS_DATABASE_URL=sqlite+aiosqlite:///{database_path}",
                "YTS_INFERENCE_BACKEND=cloud",
                "YTS_DEFAULT_TEXT_MODEL=deepseek/deepseek-chat",
                "YTS_DEEPSEEK_API_KEY=sk-deepseek-test",
                "YTS_OPENAI_API_KEY=sk-openai-test",
                "YTS_GATEWAY_BASE_URL=http://127.0.0.1:8799",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
                "YTS_LANGGRAPH_CHECKPOINT_BACKEND=memory",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_test_local_config(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    database_path = config_dir / "test-local.db"
    (config_dir / "local.env").write_text(
        "\n".join(
            [
                "YTS_PROFILE=local",
                f"YTS_DATABASE_URL=sqlite+aiosqlite:///{database_path}",
                "YTS_INFERENCE_BACKEND=local",
                "YTS_GATEWAY_BASE_URL=http://127.0.0.1:8799",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
                "YTS_LANGGRAPH_CHECKPOINT_BACKEND=memory",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def pytest_configure(config: pytest.Config) -> None:
    del config
    global _COLLECTION_CONFIG, _ORIGINAL_YTS_ENV

    if _COLLECTION_CONFIG is not None:
        return
    _ORIGINAL_YTS_ENV = {
        name: value for name, value in os.environ.items() if name.startswith("YTS_")
    }
    for name in _ORIGINAL_YTS_ENV:
        os.environ.pop(name)

    _COLLECTION_CONFIG = tempfile.TemporaryDirectory(prefix="yts-pytest-config-")
    config_dir = Path(_COLLECTION_CONFIG.name)
    _write_test_cloud_config(config_dir)
    os.environ["YTS_CONFIG_DIR"] = str(config_dir)


def pytest_unconfigure(config: pytest.Config) -> None:
    del config
    global _COLLECTION_CONFIG

    for name in tuple(os.environ):
        if name.startswith("YTS_"):
            os.environ.pop(name)
    os.environ.update(_ORIGINAL_YTS_ENV)
    if _COLLECTION_CONFIG is not None:
        _COLLECTION_CONFIG.cleanup()
        _COLLECTION_CONFIG = None


@pytest.fixture(autouse=True)
def reset_cached_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Path]:
    from yts_core.config import get_settings

    for name in tuple(os.environ):
        if name.startswith("YTS_"):
            monkeypatch.delenv(name)

    config_dir = tmp_path / "test-profile-config"
    _write_test_cloud_config(config_dir)
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))
    get_settings.cache_clear()
    yield config_dir
    get_settings.cache_clear()


def reset_cached_db_engine() -> None:
    from yts_server.db.session import get_engine, get_sessionmaker

    if get_engine.cache_info().currsize:
        engine = get_engine()
        with suppress(Exception):
            asyncio.run(engine.dispose())
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
