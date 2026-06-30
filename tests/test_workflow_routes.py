from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from conftest import reset_cached_db_engine
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from yts_core.inference import TextResult
from yts_core.orchestration.flows.pro_lyrics import PRO_STAGE_ORDER
from yts_server.main import create_app
from yts_server.routes import workflow as workflow_route


@pytest.fixture(autouse=True)
def local_workflow_profile(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    db_path = tmp_path / "yts-workflow-test.db"
    monkeypatch.setenv("YTS_PROFILE", "local")
    monkeypatch.setenv("YTS_BILLING_ENABLED", "false")
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def test_workflow_template_route_returns_locked_template() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/workflows/pro_creation_hitl_v1/template")

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"] == "pro_creation_hitl_v1"
    assert body["capabilities"]["locked_edges"] is True
    assert [node["id"] for node in body["nodes"] if node["type"] == "pro_stage"] == list(PRO_STAGE_ORDER)
    assert [node["id"] for node in body["nodes"] if node["type"].startswith("hitl_")] == [
        "brief_approval",
        "final_review",
    ]


def test_workflow_template_route_rejects_unknown_workflow() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/workflows/unknown/template")

    assert response.status_code == 404
    assert response.json()["detail"] == "unsupported workflow_id: unknown"


def test_workflow_routes_accept_desktop_cors_preflight() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/workflows/pro_creation_hitl_v1/template",
            headers={
                "Origin": "http://127.0.0.1:1420",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"


def test_workflow_run_route_returns_explicit_model_error(monkeypatch) -> None:
    checkpointer = InMemorySaver()
    monkeypatch.setattr(workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer)
    monkeypatch.setattr(workflow_route, "make_backend", lambda: BadJsonBackend())
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            json={
                "thread_id": "bad-json-thread",
                "user_prompt": "下雨的午后，大雨倾盆，思念远方的故人",
            },
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "parse_intent must return a strict JSON object" in detail
    assert "line 1 column 1" in detail
    assert "not json" in detail


def test_workflow_run_route_logs_explicit_model_error(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="yts_server.routes.workflow")
    checkpointer = InMemorySaver()
    monkeypatch.setattr(workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer)
    monkeypatch.setattr(workflow_route, "make_backend", lambda: BadJsonBackend())

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            json={
                "thread_id": "bad-json-thread",
                "user_prompt": "下雨的午后，大雨倾盆，思念远方的故人",
            },
        )

    assert response.status_code == 422
    assert "Workflow run failed" in caplog.text
    assert "workflow_id=pro_creation_hitl_v1" in caplog.text
    assert "thread_id=bad-json-thread" in caplog.text
    assert "parse_intent must return a strict JSON object" in caplog.text


def test_workflow_validation_error_logs_request_body(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="yts_server.errors")

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            json={"thread_id": "missing-user-prompt"},
        )

    assert response.status_code == 422
    assert "Request validation failed" in caplog.text
    assert "path=/api/workflows/pro_creation_hitl_v1/threads" in caplog.text
    assert "field=user_prompt" in caplog.text
    assert 'body={"thread_id":"missing-user-prompt"}' in caplog.text


def test_workflow_run_resume_trace_routes(monkeypatch) -> None:
    checkpointer = InMemorySaver()
    monkeypatch.setattr(workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer)
    monkeypatch.setattr(workflow_route, "make_backend", lambda: FakeRouteBackend())
    with TestClient(create_app()) as client:
        run_response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            json={"thread_id": "route-thread", "user_prompt": "下雨的午后，大雨倾盆，思念远方的故人"},
        )
        assert run_response.status_code == 200
        assert run_response.json()["waiting"]["node_id"] == "brief_approval"

        resume_response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads/route-thread/resume",
            json={"node_id": "brief_approval", "action": "approve"},
        )
        assert resume_response.status_code == 200
        assert resume_response.json()["waiting"]["node_id"] == "final_review"

        trace_response = client.get("/api/workflows/pro_creation_hitl_v1/threads/route-thread/trace")
        assert trace_response.status_code == 200
        assert trace_response.json()["nodes"][-1]["node_id"] == "final_review"
        assert "generate_lyrics" in [node["node_id"] for node in trace_response.json()["nodes"]]


class FakeRouteBackend:
    name = "fake-route-pro"

    def __init__(self) -> None:
        from test_creation_graph_pro import _PAYLOADS

        self.payloads = _PAYLOADS

    async def generate_text(self, messages, *, model=None, fallbacks=None, response_format=None) -> TextResult:
        import json

        marker = "YTS_PRO_STAGE:"
        content = messages[-1]["content"]
        stage = content.split(marker, 1)[1].splitlines()[0].strip()
        return TextResult(text=json.dumps(self.payloads[stage], ensure_ascii=False), provider="fake", model="fake")


class BadJsonBackend:
    name = "bad-json"

    async def generate_text(self, messages, *, model=None, fallbacks=None, response_format=None) -> TextResult:
        return TextResult(text="not json", provider="fake", model="fake")
