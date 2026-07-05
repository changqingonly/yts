from __future__ import annotations

import hashlib
import io
import os
import sqlite3
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


def test_default_playlist_append_allows_duplicate_content_hash_and_assigns_positions() -> None:
    audio_bytes = wav_bytes()
    expected_hash = hashlib.sha256(audio_bytes).hexdigest()

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "playlist@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        upload = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        )
        assert upload.status_code == 200, upload.text

        default_playlist = client.post(
            "/api/music/playlists/default",
            headers=headers,
            json={"scope": "cloud"},
        )
        assert default_playlist.status_code == 200, default_playlist.text
        playlist_id = default_playlist.json()["id"]

        appended = client.post(
            f"/api/music/playlists/{playlist_id}/items",
            headers=headers,
            json={
                "items": [
                    {
                        "content_hash": expected_hash,
                        "title_alias": "雨声 A",
                        "artist_alias": "",
                        "device_id": "device-a",
                    },
                    {
                        "content_hash": expected_hash,
                        "title_alias": "雨声 B",
                        "artist_alias": "me",
                        "device_id": "device-a",
                    },
                ]
            },
        )
        assert appended.status_code == 200, appended.text
        items = appended.json()["items"]
        assert [item["position"] for item in items] == [1, 2]
        assert items[0]["content_hash"] == expected_hash
        assert items[1]["content_hash"] == expected_hash
        assert items[0]["title_alias"] == "雨声 A"
        assert items[0]["meta_song"]["content_hash"] == expected_hash

        listed = client.get(f"/api/music/playlists/{playlist_id}/items", headers=headers)
        assert listed.status_code == 200, listed.text
        assert [item["position"] for item in listed.json()["items"]] == [1, 2]
        assert listed.json()["playlist"]["item_count"] == 2


def test_reorder_playlist_items_rewrites_continuous_positions() -> None:
    audio_bytes = wav_bytes()
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "reorder@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        content_hash = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        ).json()["content_hash"]
        playlist_id = client.post(
            "/api/music/playlists/default",
            headers=headers,
            json={"scope": "cloud"},
        ).json()["id"]
        appended = client.post(
            f"/api/music/playlists/{playlist_id}/items",
            headers=headers,
            json={
                "items": [
                    {
                        "content_hash": content_hash,
                        "title_alias": "一",
                        "artist_alias": "",
                        "device_id": "d",
                    },
                    {
                        "content_hash": content_hash,
                        "title_alias": "二",
                        "artist_alias": "",
                        "device_id": "d",
                    },
                    {
                        "content_hash": content_hash,
                        "title_alias": "三",
                        "artist_alias": "",
                        "device_id": "d",
                    },
                ]
            },
        ).json()["items"]
        ordered_ids = [appended[2]["id"], appended[0]["id"], appended[1]["id"]]

        reordered = client.post(
            f"/api/music/playlists/{playlist_id}/items/reorder",
            headers=headers,
            json={"ordered_item_ids": ordered_ids},
        )
        assert reordered.status_code == 200, reordered.text
        assert [(item["id"], item["position"]) for item in reordered.json()["items"]] == [
            (ordered_ids[0], 1),
            (ordered_ids[1], 2),
            (ordered_ids[2], 3),
        ]


def test_playlist_append_rejects_when_item_limit_exceeded() -> None:
    audio_bytes = wav_bytes()
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "limit@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        content_hash = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        ).json()["content_hash"]
        playlist_id = client.post(
            "/api/music/playlists/default",
            headers=headers,
            json={"scope": "cloud"},
        ).json()["id"]
        payload = {
            "items": [
                {
                    "content_hash": content_hash,
                    "title_alias": f"song-{index}",
                    "artist_alias": "",
                    "device_id": "device-a",
                }
                for index in range(2001)
            ]
        }

        response = client.post(f"/api/music/playlists/{playlist_id}/items", headers=headers, json=payload)
        assert response.status_code == 400
        assert response.json()["code"] == "playlist_item_limit_exceeded"


def test_playlist_append_requires_current_user_song_owner() -> None:
    audio_bytes = wav_bytes()
    with TestClient(create_app()) as client:
        owner_token = register_via_test_crypto(client, "owner@example.com", "Password123")[
            "access_token"
        ]
        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        content_hash = client.post(
            "/api/music/upload",
            headers=owner_headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        ).json()["content_hash"]

        other_token = register_via_test_crypto(client, "other@example.com", "Password123")[
            "access_token"
        ]
        other_headers = {"Authorization": f"Bearer {other_token}"}
        playlist_id = client.post(
            "/api/music/playlists/default",
            headers=other_headers,
            json={"scope": "cloud"},
        ).json()["id"]
        response = client.post(
            f"/api/music/playlists/{playlist_id}/items",
            headers=other_headers,
            json={
                "items": [
                    {
                        "content_hash": content_hash,
                        "title_alias": "borrowed",
                        "artist_alias": "",
                        "device_id": "device-b",
                    }
                ]
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "song_owner_required"


def test_bootstrap_upgrades_existing_playlist_tables() -> None:
    db_url = os.environ["YTS_DATABASE_URL"]
    db_path = db_url.removeprefix("sqlite+aiosqlite:///")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE music_playlist (
                id VARCHAR(128) PRIMARY KEY,
                user_uuid VARCHAR(64) NOT NULL,
                name VARCHAR(255) NOT NULL,
                updated_at_ms BIGINT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE music_playlist_item (
                id VARCHAR(128) PRIMARY KEY,
                user_uuid VARCHAR(64) NOT NULL,
                playlist_id VARCHAR(128) NOT NULL,
                source VARCHAR(64) NOT NULL,
                source_ref TEXT NOT NULL,
                title VARCHAR(255),
                artist VARCHAR(255),
                duration_ms INTEGER,
                cover_url VARCHAR(512),
                position FLOAT NOT NULL,
                added_at_ms BIGINT NOT NULL,
                updated_at_ms BIGINT NOT NULL,
                deleted_at_ms BIGINT,
                op_clock BIGINT NOT NULL,
                device_id VARCHAR(128) NOT NULL,
                content_hash VARCHAR(64),
                size_bytes BIGINT,
                mime VARCHAR(128)
            )
            """
        )

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "upgrade@example.com", "Password123")[
            "access_token"
        ]
        response = client.post(
            "/api/music/playlists/default",
            headers={"Authorization": f"Bearer {token}"},
            json={"scope": "cloud"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["scope"] == "cloud"
        assert response.json()["item_count"] == 0


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
            f"/api/music/file/{expected_hash}",
            headers=headers,
        )
        assert downloaded.status_code == 200
        assert downloaded.content == audio_bytes
