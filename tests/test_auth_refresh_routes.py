from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import reset_cached_db_engine
from fastapi.testclient import TestClient
from test_auth_profile_routes import register_via_test_crypto
from yts_server.main import create_app


@pytest.fixture(autouse=True)
def isolated_sqlite_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    db_path = tmp_path / "yts-refresh-test.db"
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("YTS_AUTH_JWT_SECRET", "test-secret-that-is-long-enough-for-hs256-tests")
    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def test_register_sets_http_only_device_and_refresh_cookies() -> None:
    with TestClient(create_app()) as client:
        register_via_test_crypto(client, "Cookie@Example.com", "Password123")

        assert client.cookies.get("yts-device")
        assert client.cookies.get("yts-refresh")


def test_refresh_rotates_cookie_and_issues_access_token() -> None:
    with TestClient(create_app()) as client:
        register_via_test_crypto(client, "refresh@example.com", "Password123")
        old_refresh = client.cookies.get("yts-refresh")

        response = client.post(
            "/api/auth/refresh", headers={"X-Refresh-Request-ID": "refresh-request-1"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["access_token"]
        assert client.cookies.get("yts-refresh") != old_refresh


def test_access_token_rejects_device_cookie_mismatch() -> None:
    with TestClient(create_app()) as client:
        registered = register_via_test_crypto(client, "device@example.com", "Password123")
        client.cookies.delete("yts-device")
        client.cookies.set("yts-device", "wrong-device")

        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {registered['access_token']}"},
        )

        assert response.status_code == 401


def test_refresh_replay_revokes_the_session() -> None:
    with TestClient(create_app()) as client:
        register_via_test_crypto(client, "replay@example.com", "Password123")
        old_refresh = client.cookies.get("yts-refresh")
        first = client.post(
            "/api/auth/refresh", headers={"X-Refresh-Request-ID": "rotation-1"}
        )
        assert first.status_code == 200
        current_refresh = client.cookies.get("yts-refresh")

        client.cookies.delete("yts-refresh")
        client.cookies.set("yts-refresh", old_refresh, path="/api/auth")
        replay = client.post(
            "/api/auth/refresh", headers={"X-Refresh-Request-ID": "rotation-2"}
        )
        assert replay.status_code == 401

        client.cookies.delete("yts-refresh")
        client.cookies.set("yts-refresh", current_refresh, path="/api/auth")
        rejected = client.post(
            "/api/auth/refresh", headers={"X-Refresh-Request-ID": "rotation-3"}
        )
        assert rejected.status_code == 401


def test_email_is_normalized_for_uniqueness() -> None:
    with TestClient(create_app()) as client:
        register_via_test_crypto(client, "Case@Example.com", "Password123")
        key = client.get("/api/auth/register_key").json()

        response = client.get("/api/auth/register_check", params={"email": "case@example.com"})

        assert response.status_code == 200
        assert response.json() == {"email_ok": True, "email_msg": ""}
        assert key["key_id"]
