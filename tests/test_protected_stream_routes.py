from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import reset_cached_db_engine
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from yts_server.main import create_app


@pytest.fixture(autouse=True)
def cloud_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    monkeypatch.setenv("YTS_PROFILE", "cloud")
    monkeypatch.setenv("YTS_BILLING_ENABLED", "true")
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'protected.db'}")
    monkeypatch.setenv("YTS_AUTH_JWT_SECRET", "test-secret-that-is-long-enough-for-hs256-tests")
    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def test_cloud_image_generation_rejects_anonymous_request() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/image", json={"prompt": "rain"})
    assert response.status_code == 401


def test_cloud_music_stream_rejects_anonymous_request_before_generation() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect("/music/stream") as websocket:
            websocket.send_json({"type": "start", "prompt": "rain", "seconds": 8})
            message = websocket.receive_json()
    assert message["code"] == "unauthorized"


def test_music_stream_rejects_disallowed_origin_before_accept() -> None:
    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/music/stream", headers={"Origin": "https://attacker.invalid"}
            ):
                pass


def test_transport_rpc_rejects_disallowed_origin_before_accept() -> None:
    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/api/transport/rpc", headers={"Origin": "https://attacker.invalid"}
            ):
                pass


def test_transport_rpc_refuses_authentication_proxying() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect("/api/transport/rpc") as websocket:
            websocket.send_json(
                {
                    "id": "refresh",
                    "method": "POST",
                    "path": "/api/auth/refresh",
                    "headers": {"X-Refresh-Request-ID": "attack"},
                    "body": None,
                }
            )
            message = websocket.receive_json()
    assert message["status"] == 403
