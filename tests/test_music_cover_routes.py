from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import reset_cached_db_engine
from fastapi.testclient import TestClient
from sqlalchemy import UniqueConstraint
from test_auth_profile_routes import register_via_test_crypto
from yts_server.db.models import MusicCoverJob
from yts_server.db.session import get_sessionmaker
from yts_server.domains.music_covers import _mark_ready
from yts_server.main import create_app


@pytest.fixture(autouse=True)
def isolated_local_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    async def available_image_model(self) -> tuple[bool, str | None]:
        return True, None

    monkeypatch.setattr(
        "yts_core.inference.gateway_adapter.GatewayInference.image_status",
        available_image_model,
        raising=False,
    )
    monkeypatch.setenv("YTS_PROFILE", "local")
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'yts.db'}")
    monkeypatch.setenv("YTS_AUTH_JWT_SECRET", "test-secret-that-is-long-enough-for-hs256-tests")
    monkeypatch.setenv("YTS_LOCAL_IMPORT_STORAGE_DIR", str(tmp_path / "imports"))
    monkeypatch.setenv("YTS_PLAYBACK_RENDITION_STORAGE_DIR", str(tmp_path / "renditions"))
    monkeypatch.setenv("YTS_MUSIC_COVER_STORAGE_DIR", str(tmp_path / "covers"))
    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def test_cover_job_schema_enforces_one_job_per_user_song_epoch() -> None:
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in MusicCoverJob.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("user_uuid", "content_hash", "generation_epoch") in unique_columns


def test_ensure_reports_unavailable_without_enqueuing_when_local_image_model_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_image_model(self) -> tuple[bool, str | None]:
        return False, "local image model is not installed"

    monkeypatch.setattr(
        "yts_core.inference.gateway_adapter.GatewayInference.image_status",
        unavailable_image_model,
        raising=False,
    )
    with TestClient(create_app()) as client:
        headers, content_hash = _upload_song(client)
        response = client.post(
            f"/api/music/covers/{content_hash}/ensure",
            headers=headers,
            json={"trigger_source": "system"},
        )

        assert response.status_code == 200, response.text
        assert response.json() == {
            "content_hash": content_hash,
            "generation_epoch": 1,
            "status": "unavailable",
            "error_code": "local_image_model_unavailable",
            "error_message": "local image model is not installed",
            "cover_url": None,
        }


def test_system_and_user_ensure_reuse_the_same_local_cover_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_cover_work(*args, **kwargs) -> bool:
        return False

    monkeypatch.setattr("yts_server.domains.music_covers.process_next_cover_job", no_cover_work)
    with TestClient(create_app()) as client:
        headers, content_hash = _upload_song(client)
        system = client.post(
            f"/api/music/covers/{content_hash}/ensure",
            headers=headers,
            json={"trigger_source": "system"},
        )
        user = client.post(
            f"/api/music/covers/{content_hash}/ensure",
            headers=headers,
            json={"trigger_source": "user"},
        )

        assert system.status_code == 200, system.text
        assert user.status_code == 200, user.text
        assert system.json()["job_id"] == user.json()["job_id"]
        assert system.json()["generation_epoch"] == 1
        assert user.json()["priority"] == 100


def test_delete_suppresses_ensure_until_idempotent_regenerate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_cover_work(*args, **kwargs) -> bool:
        return False

    monkeypatch.setattr("yts_server.domains.music_covers.process_next_cover_job", no_cover_work)
    with TestClient(create_app()) as client:
        headers, content_hash = _upload_song(client)
        first = client.post(
            f"/api/music/covers/{content_hash}/ensure",
            headers=headers,
            json={"trigger_source": "system"},
        )
        deleted = client.delete(f"/api/music/covers/{content_hash}", headers=headers)
        suppressed = client.post(
            f"/api/music/covers/{content_hash}/ensure",
            headers=headers,
            json={"trigger_source": "system"},
        )
        regenerated = client.post(
            f"/api/music/covers/{content_hash}/regenerate",
            headers=headers,
            json={"request_id": "regenerate-click-1"},
        )
        repeated = client.post(
            f"/api/music/covers/{content_hash}/regenerate",
            headers=headers,
            json={"request_id": "regenerate-click-1"},
        )

        assert first.status_code == 200, first.text
        assert deleted.status_code == 200, deleted.text
        assert suppressed.status_code == 200, suppressed.text
        assert suppressed.json()["status"] == "suppressed"
        assert regenerated.status_code == 200, regenerated.text
        assert repeated.status_code == 200, repeated.text
        assert regenerated.json()["generation_epoch"] == 2
        assert repeated.json()["job_id"] == regenerated.json()["job_id"]


def test_retry_requeues_the_same_failed_cover_job(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_cover_work(*args, **kwargs) -> bool:
        return False

    monkeypatch.setattr("yts_server.domains.music_covers.process_next_cover_job", no_cover_work)
    with TestClient(create_app()) as client:
        headers, content_hash = _upload_song(client)
        ensured = client.post(
            f"/api/music/covers/{content_hash}/ensure",
            headers=headers,
            json={"trigger_source": "system"},
        ).json()
        db_path = os.environ["YTS_DATABASE_URL"].removeprefix("sqlite+aiosqlite:///")
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE music_cover_job SET status = 'failed', error_code = 'gateway_timeout' "
                "WHERE id = ?",
                (ensured["job_id"],),
            )
        retried = client.post(f"/api/music/covers/{content_hash}/retry", headers=headers)

        assert retried.status_code == 200, retried.text
        assert retried.json()["job_id"] == ensured["job_id"]
        assert retried.json()["generation_epoch"] == 1
        assert retried.json()["status"] == "queued"


def test_cancelled_job_rejects_late_ready_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def no_cover_work(*args, **kwargs) -> bool:
        return False

    monkeypatch.setattr("yts_server.domains.music_covers.process_next_cover_job", no_cover_work)
    with TestClient(create_app()) as client:
        headers, content_hash = _upload_song(client)
        job_id = client.post(
            f"/api/music/covers/{content_hash}/ensure",
            headers=headers,
            json={"trigger_source": "system"},
        ).json()["job_id"]
        db_path = os.environ["YTS_DATABASE_URL"].removeprefix("sqlite+aiosqlite:///")
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE music_cover_job SET status = 'cancelled' WHERE id = ?", (job_id,)
            )
        accepted = asyncio.run(
            _mark_ready(get_sessionmaker(), job_id, tmp_path / "late.png", "deadbeef")
        )

        assert accepted is False


def _upload_song(client: TestClient) -> tuple[dict[str, str], str]:
    token = register_via_test_crypto(client, "cover@example.com", "Password123")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    audio = (Path(__file__).parent / "fixtures/audio/sample.wav").read_bytes()
    response = client.post(
        "/api/music/upload",
        headers=headers,
        files={"file": ("sample.wav", audio, "audio/wav")},
    )
    assert response.status_code == 200, response.text
    return headers, hashlib.sha256(audio).hexdigest()
