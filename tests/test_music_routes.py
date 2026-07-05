from __future__ import annotations

import hashlib
import io
import wave
from collections.abc import Iterator

import pytest
from conftest import reset_cached_db_engine
from fastapi.testclient import TestClient
from test_auth_profile_routes import register_via_test_crypto
from yts_server.main import create_app


@pytest.fixture(autouse=True)
def isolated_sqlite_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    db_path = tmp_path / "yts-test.db"
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv(
        "YTS_AUTH_JWT_SECRET",
        "test-secret-that-is-long-enough-for-hs256-tests",
    )
    monkeypatch.setenv("YTS_LOCAL_IMPORT_STORAGE_DIR", str(tmp_path / "local-imports"))

    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def wav_bytes(duration_seconds: float = 0.25, sample_rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    frame_count = int(duration_seconds * sample_rate)
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def test_upload_song_extracts_meta_song_and_reuses_content_hash() -> None:
    audio_bytes = wav_bytes()
    expected_hash = hashlib.sha256(audio_bytes).hexdigest()

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "meta@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}

        first = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["content_hash"] == expected_hash
        assert body["filename"] == "rain.wav"
        assert body["size_bytes"] == len(audio_bytes)
        assert body["deduplicated"] is False
        assert body["meta_song"]["content_hash"] == expected_hash
        assert body["meta_song"]["file_format"] == "wav"
        assert body["meta_song"]["duration_ms"] in range(200, 350)
        assert body["meta_song"]["sample_rate_hz"] == 8000
        assert body["meta_song"]["channels"] == 1
        assert body["meta_song"]["codec_name"] == "pcm_s16le"

        second = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain-copy.wav", audio_bytes, "audio/wav")},
        )
        assert second.status_code == 200, second.text
        assert second.json()["content_hash"] == expected_hash
        assert second.json()["deduplicated"] is True
        assert second.json()["meta_song"] == body["meta_song"]


def test_upload_song_rejects_empty_file() -> None:
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "empty-song@example.com", "Password123")[
            "access_token"
        ]
        response = client.post(
            "/api/music/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("empty.wav", b"", "audio/wav")},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "empty_file"


def test_playlist_sync_accepts_remote_song_and_rejects_unowned_local_file() -> None:
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "music@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}

        remote_payload = {
            "uploads": [
                {
                    "id": "track-remote-1",
                    "playlist_id": "",
                    "source": "remote_song",
                    "source_ref": "/music/rain.mp3",
                    "title": "雨声",
                    "artist": "YTS",
                    "duration_ms": 180000,
                    "cover_url": None,
                    "position": 1024,
                    "added_at_ms": 1782600000000,
                    "updated_at_ms": 1782600000000,
                    "deleted_at_ms": None,
                    "client_op_clock": 1,
                    "device_id": "device-a",
                }
            ]
        }
        synced = client.post("/api/music/playlist/sync", headers=headers, json=remote_payload)
        assert synced.status_code == 200, synced.text
        body = synced.json()
        assert body["server_clock"] == 1
        assert body["upload_results"] == [{"status": "accepted", "op_clock": 1}]
        assert body["changes"][0]["title"] == "雨声"

        local_payload = {
            "uploads": [
                {
                    **remote_payload["uploads"][0],
                    "id": "track-local-1",
                    "source": "local_file",
                    "source_ref": "missing",
                    "content_hash": "a" * 64,
                    "client_op_clock": 1,
                }
            ]
        }
        rejected = client.post("/api/music/playlist/sync", headers=headers, json=local_payload)
        assert rejected.status_code == 400
        assert "local import" in rejected.json()["detail"]


def test_local_import_upload_allows_owned_local_file_sync() -> None:
    audio_bytes = b"fake audio bytes"
    expected_hash = hashlib.sha256(audio_bytes).hexdigest()

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "local@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}

        uploaded = client.post(
            "/api/music/local_import/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["content_hash"] == expected_hash

        synced = client.post(
            "/api/music/playlist/sync",
            headers=headers,
            json={
                "uploads": [
                    {
                        "id": "track-local-owned",
                        "playlist_id": "",
                        "source": "local_file",
                        "source_ref": expected_hash,
                        "title": "本地雨声",
                        "artist": "me",
                        "duration_ms": None,
                        "cover_url": None,
                        "position": 1024,
                        "added_at_ms": 1782600000000,
                        "updated_at_ms": 1782600000000,
                        "deleted_at_ms": None,
                        "client_op_clock": 1,
                        "device_id": "device-a",
                        "content_hash": expected_hash,
                        "size_bytes": len(audio_bytes),
                        "mime": "audio/wav",
                    }
                ]
            },
        )
        assert synced.status_code == 200, synced.text
        assert synced.json()["changes"][0]["content_hash"] == expected_hash

        downloaded = client.get(
            f"/api/music/local_import/file/{expected_hash}",
            headers=headers,
        )
        assert downloaded.status_code == 200
        assert downloaded.content == audio_bytes
