from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import reset_cached_db_engine
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_auth_profile_routes import register_via_test_crypto
from test_workflow_routes import BadJsonBackend, FakeRouteBackend
from yts_core.schemas.creation import CreationResult, InspirationResult
from yts_server.main import create_app
from yts_server.routes import creation as creation_route
from yts_server.routes import workflow as workflow_route


@pytest.fixture(autouse=True)
def isolated_cloud_sqlite_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    db_path = tmp_path / "yts-test.db"
    monkeypatch.setenv("YTS_PROFILE", "cloud")
    monkeypatch.setenv("YTS_BILLING_ENABLED", "true")
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv(
        "YTS_AUTH_JWT_SECRET",
        "test-secret-that-is-long-enough-for-hs256-tests",
    )
    monkeypatch.setattr(
        workflow_route,
        "build_langgraph_checkpointer",
        lambda settings: InMemorySaver(),
    )
    monkeypatch.setattr(
        creation_route,
        "build_langgraph_checkpointer",
        lambda settings: InMemorySaver(),
    )

    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def test_cloud_workflow_requires_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workflow_route, "make_backend", lambda: FakeRouteBackend())

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            json={"thread_id": "cloud-auth", "user_prompt": "雨天"},
        )

    assert response.status_code == 401


def test_cloud_workflow_reserves_and_captures_credit(monkeypatch: pytest.MonkeyPatch) -> None:
    checkpointer = InMemorySaver()
    monkeypatch.setattr(workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer)
    monkeypatch.setattr(workflow_route, "make_backend", lambda: FakeRouteBackend())

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "billing@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}

        before = client.get("/api/credits/balance", headers=headers).json()["balance"]
        run_response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            headers=headers,
            json={"thread_id": "cloud-billing", "user_prompt": "下雨的午后，大雨倾盆，思念远方的故人"},
        )
        assert run_response.status_code == 200

        resume_response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads/cloud-billing/resume",
            headers=headers,
            json={"node_id": "brief_approval", "action": "approve"},
        )
        assert resume_response.status_code == 200

        after = client.get("/api/credits/balance", headers=headers).json()
        assert after["balance"] == before - 6
        assert after["frozen_balance"] == 0

        usage = client.get("/api/usage/daily", headers=headers).json()
        assert usage["lyrics"]["used"] == 2


def test_cloud_workflow_releases_credit_when_model_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workflow_route, "make_backend", lambda: BadJsonBackend())

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "release@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        before = client.get("/api/credits/balance", headers=headers).json()["balance"]

        response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            headers=headers,
            json={"thread_id": "cloud-release", "user_prompt": "下雨的午后"},
        )
        assert response.status_code == 422

        after = client.get("/api/credits/balance", headers=headers).json()
        assert after["balance"] == before
        assert after["frozen_balance"] == 0
        assert client.get("/api/usage/daily", headers=headers).json()["lyrics"]["used"] == 1


def test_cloud_creation_endpoint_requires_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_creation(req, *, checkpointer=None):
        return CreationResult(title="雨", lyrics="歌词", style="style")

    monkeypatch.setattr(creation_route, "run_creation", fake_run_creation)

    with TestClient(create_app()) as client:
        response = client.post("/api/creation", json={"user_prompt": "雨天"})

    assert response.status_code == 401


def test_cloud_creation_endpoint_captures_lyrics_credit_and_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_creation(req, *, checkpointer=None):
        return CreationResult(title="雨", lyrics="歌词", style="style")

    monkeypatch.setattr(creation_route, "run_creation", fake_run_creation)

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "creation@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        before = client.get("/api/credits/balance", headers=headers).json()["balance"]

        response = client.post(
            "/api/creation",
            headers=headers,
            json={"user_prompt": "雨天"},
        )
        assert response.status_code == 200

        balance = client.get("/api/credits/balance", headers=headers).json()
        assert balance["balance"] == before - 3
        assert balance["frozen_balance"] == 0
        assert client.get("/api/usage/daily", headers=headers).json()["lyrics"]["used"] == 1


def test_cloud_inspiration_endpoint_captures_inspiration_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_inspiration(req):
        return InspirationResult(inspiration="雨声里有旧人")

    monkeypatch.setattr(creation_route, "run_inspiration", fake_run_inspiration)

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "inspiration@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        before = client.get("/api/credits/balance", headers=headers).json()["balance"]

        response = client.post(
            "/api/creation/inspiration/fill",
            headers=headers,
            json={"current_prompt": "雨天"},
        )
        assert response.status_code == 200

        balance = client.get("/api/credits/balance", headers=headers).json()
        assert balance["balance"] == before - 1
        assert balance["frozen_balance"] == 0
