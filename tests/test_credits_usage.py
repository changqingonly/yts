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


def test_credit_balance_ledger_and_daily_usage_are_created_for_registered_user() -> None:
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "credit@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}

        balance = client.get("/api/credits/balance", headers=headers)
        assert balance.status_code == 200
        assert balance.json()["balance"] >= 50
        assert balance.json()["frozen_balance"] == 0

        ledger = client.get("/api/credits/ledger", headers=headers)
        assert ledger.status_code == 200
        assert ledger.json()[0]["biz_type"] == "welcome_register"

        usage = client.get("/api/usage/daily", headers=headers)
        assert usage.status_code == 200
        assert usage.json()["lyrics"]["limit"] == 100
        assert usage.json()["lyrics"]["used"] == 0
        assert usage.json()["images"]["limit"] == 100
        assert usage.json()["audio_effects"]["limit"] == 100


def test_image_and_audio_effect_generation_fail_explicitly_when_provider_missing() -> None:
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "provider@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}

        image = client.post("/api/images/generate", headers=headers, json={"prompt": "rain"})
        assert image.status_code == 501
        assert image.json()["code"] == "provider_not_configured"
        assert image.json()["field"] == "images"

        audio = client.post(
            "/api/audio-effects/generate",
            headers=headers,
            json={"prompt": "rain hit"},
        )
        assert audio.status_code == 501
        assert audio.json()["code"] == "provider_not_configured"
        assert audio.json()["field"] == "audio_effects"
