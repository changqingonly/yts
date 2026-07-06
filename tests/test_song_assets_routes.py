from __future__ import annotations

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

    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def test_song_asset_crud_requires_owner() -> None:
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "song@example.com", "Password123")["access_token"]
        other_token = register_via_test_crypto(client, "other@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        other_headers = {"Authorization": f"Bearer {other_token}"}

        created = client.post(
            "/api/song/save",
            headers=headers,
            json={
                "name": "雨落的声音像你",
                "prompt": "雨天午后想念故人",
                "lyric_prompt": "[Verse 1]\n雨落在窗沿",
                "style_prompt": "Mandarin emotional pop ballad",
                "llm": "fake",
            },
        )
        assert created.status_code == 200
        song_id = created.json()["id"]

        listed = client.get("/api/song/list", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["name"] == "雨落的声音像你"
        assert listed.json()[0]["prompt"] == "雨天午后想念故人"

        detail = client.get(f"/api/song/{song_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["style_prompt"] == "Mandarin emotional pop ballad"
        assert detail.json()["lyric_prompt"] == "[Verse 1]\n雨落在窗沿"

        forbidden = client.get(f"/api/song/{song_id}", headers=other_headers)
        assert forbidden.status_code == 404

        updated = client.put(
            f"/api/song/{song_id}",
            headers=headers,
            json={"name": "雨声像你", "lyric_prompt": "[Chorus]\n雨落的声音像你"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "雨声像你"
        assert updated.json()["lyric_prompt"] == "[Chorus]\n雨落的声音像你"

        deleted = client.delete(f"/api/song/{song_id}", headers=headers)
        assert deleted.status_code == 200

        missing = client.get(f"/api/song/{song_id}", headers=headers)
        assert missing.status_code == 404
