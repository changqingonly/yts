from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import reset_cached_db_engine
from fastapi.testclient import TestClient
from yts_server import main as server_main


@pytest.fixture(autouse=True)
def isolated_lifespan_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    db_path = tmp_path / "lifespan.db"
    monkeypatch.setenv("YTS_PROFILE", "local")
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("YTS_INFERENCE_BACKEND", "local")
    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def test_lifespan_runs_db_bootstrap_without_servctl_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def create_tables() -> None:
        calls.append("create_all_tables")

    monkeypatch.delenv("YTS_SKIP_STARTUP_DB_BOOTSTRAP", raising=False)
    monkeypatch.setattr(server_main, "create_all_tables", create_tables)

    with TestClient(server_main.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert calls == ["create_all_tables"]


def test_lifespan_skips_db_bootstrap_after_servctl_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def create_tables() -> None:
        raise AssertionError("servctl preflight already completed DB bootstrap")

    monkeypatch.setenv("YTS_SKIP_STARTUP_DB_BOOTSTRAP", "1")
    monkeypatch.setattr(server_main, "create_all_tables", create_tables)

    with TestClient(server_main.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
