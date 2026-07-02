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
    assert [node["id"] for node in body["nodes"] if node["type"] == "pro_stage"] == list(
        PRO_STAGE_ORDER
    )
    assert [node["id"] for node in body["nodes"] if node["type"].startswith("hitl_")] == [
        "final_review"
    ]
    assert "brief_approval" not in [node["id"] for node in body["nodes"]]


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


def test_transport_rpc_websocket_proxies_json_api_requests() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect("/api/transport/rpc") as websocket:
            websocket.send_json(
                {
                    "id": "template-request",
                    "method": "GET",
                    "path": "/api/workflows/pro_creation_hitl_v1/template",
                    "headers": {},
                    "body": None,
                }
            )
            message = websocket.receive_json()

    assert message["id"] == "template-request"
    assert message["status"] == 200
    assert message["body"]["workflow_id"] == "pro_creation_hitl_v1"


def test_workflow_run_route_returns_explicit_model_error(monkeypatch) -> None:
    checkpointer = InMemorySaver()
    monkeypatch.setattr(
        workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer
    )
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
    monkeypatch.setattr(
        workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer
    )
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
    assert "workflow.run.failed" in caplog.text
    assert "'workflow_id': 'pro_creation_hitl_v1'" in caplog.text
    assert "'thread_id': 'bad-json-thread'" in caplog.text
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
    monkeypatch.setattr(
        workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer
    )
    monkeypatch.setattr(workflow_route, "make_backend", lambda: FakeRouteBackend())
    with TestClient(create_app()) as client:
        run_response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            json={
                "thread_id": "route-thread",
                "user_prompt": "下雨的午后，大雨倾盆，思念远方的故人",
            },
        )
        assert run_response.status_code == 200
        assert run_response.json()["waiting"]["node_id"] == "final_review"
        assert "brief_approval" not in [
            node["node_id"] for node in run_response.json()["trace"]["nodes"]
        ]

        trace_response = client.get(
            "/api/workflows/pro_creation_hitl_v1/threads/route-thread/trace"
        )
        assert trace_response.status_code == 200
        assert trace_response.json()["nodes"][-1]["node_id"] == "final_review"
        assert "generate_lyrics" in [node["node_id"] for node in trace_response.json()["nodes"]]


def test_workflow_history_lists_latest_thread_snapshot_after_run_and_resume(monkeypatch) -> None:
    checkpointer = InMemorySaver()
    monkeypatch.setattr(
        workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer
    )
    monkeypatch.setattr(workflow_route, "make_backend", lambda: FakeRouteBackend())

    with TestClient(create_app()) as client:
        run_response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            json={
                "thread_id": "history-thread",
                "user_prompt": "下雨的午后，大雨倾盆，思念远方的故人",
            },
        )
        assert run_response.status_code == 200

        waiting_history_response = client.get(
            "/api/workflows/pro_creation_hitl_v1/threads/history"
        )
        assert waiting_history_response.status_code == 200
        waiting_items = waiting_history_response.json()
        assert len(waiting_items) == 1
        assert waiting_items[0]["thread_id"] == "history-thread"
        assert waiting_items[0]["run_id"] == run_response.json()["run_id"]
        assert waiting_items[0]["status"] == "waiting"
        assert waiting_items[0]["title"] == "雨中故人"
        assert waiting_items[0]["user_prompt"] == "下雨的午后，大雨倾盆，思念远方的故人"
        assert waiting_items[0]["completed_nodes"] == 14
        assert waiting_items[0]["total_nodes"] == 16
        assert waiting_items[0]["last_node_id"] == "final_review"
        assert waiting_items[0]["updated_at"]

        resume_response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads/history-thread/resume",
            json={"node_id": "final_review", "action": "accept", "patch": {}},
        )
        assert resume_response.status_code == 200

        completed_history_response = client.get(
            "/api/workflows/pro_creation_hitl_v1/threads/history"
        )
        assert completed_history_response.status_code == 200
        completed_items = completed_history_response.json()
        assert len(completed_items) == 1
        assert completed_items[0]["thread_id"] == "history-thread"
        assert completed_items[0]["run_id"] == resume_response.json()["run_id"]
        assert completed_items[0]["status"] == "completed"
        assert completed_items[0]["title"] == "雨中故人"
        assert completed_items[0]["completed_nodes"] == 16
        assert completed_items[0]["total_nodes"] == 16
        assert completed_items[0]["last_node_id"] == "done"


def test_workflow_run_stream_pushes_node_trace_chunks(monkeypatch) -> None:
    checkpointer = InMemorySaver()
    monkeypatch.setattr(
        workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer
    )
    monkeypatch.setattr(workflow_route, "make_backend", lambda: FakeRouteBackend())

    with TestClient(create_app()) as client:
        with client.websocket_connect(
            "/api/workflows/pro_creation_hitl_v1/threads/stream"
        ) as websocket:
            websocket.send_json(
                {
                    "type": "run",
                    "thread_id": "stream-thread",
                    "user_prompt": "下雨的午后，大雨倾盆，思念远方的故人",
                    "node_config": {},
                }
            )
            messages = _receive_until_terminal(websocket)

    assert messages[0]["type"] == "started"
    trace_messages = [message for message in messages if message["type"] == "trace"]
    assert trace_messages
    assert [node["node_id"] for node in trace_messages[0]["trace"]["nodes"]] == ["validate_request"]
    assert any(
        message["trace"]["nodes"][-1]["node_id"] == "build_response" for message in trace_messages
    )
    terminal = messages[-1]
    assert terminal["type"] == "result"
    assert terminal["result"]["status"] == "waiting"
    assert terminal["result"]["waiting"]["node_id"] == "final_review"
    assert "brief_approval" not in [
        node["node_id"] for node in terminal["result"]["trace"]["nodes"]
    ]


def test_cloud_workflow_run_stream_returns_auth_error_without_asgi_crash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "cloud-workflow-stream-auth.db"
    monkeypatch.setenv("YTS_PROFILE", "cloud")
    monkeypatch.setenv("YTS_BILLING_ENABLED", "true")
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    reset_cached_db_engine()

    with TestClient(create_app()) as client:
        with client.websocket_connect(
            "/api/workflows/pro_creation_hitl_v1/threads/stream"
        ) as websocket:
            websocket.send_json(
                {
                    "type": "run",
                    "thread_id": "cloud-missing-token-stream",
                    "user_prompt": "下雨的午后",
                    "node_config": {},
                    "authorization": "",
                }
            )
            message = websocket.receive_json()

    assert message == {
        "type": "error",
        "code": "unauthorized",
        "detail": "missing bearer token",
    }


def test_workflow_resume_stream_pushes_node_trace_chunks(monkeypatch) -> None:
    checkpointer = InMemorySaver()
    monkeypatch.setattr(
        workflow_route, "build_langgraph_checkpointer", lambda settings: checkpointer
    )
    monkeypatch.setattr(workflow_route, "make_backend", lambda: FakeRouteBackend())

    with TestClient(create_app()) as client:
        run_response = client.post(
            "/api/workflows/pro_creation_hitl_v1/threads",
            json={
                "thread_id": "resume-stream-thread",
                "user_prompt": "下雨的午后，大雨倾盆，思念远方的故人",
            },
        )
        assert run_response.status_code == 200

        with client.websocket_connect(
            "/api/workflows/pro_creation_hitl_v1/threads/resume-stream-thread/stream"
        ) as websocket:
            websocket.send_json(
                {
                    "type": "resume",
                    "node_id": "final_review",
                    "action": "accept",
                    "patch": {},
                }
            )
            messages = _receive_until_terminal(websocket)

    assert messages[0]["type"] == "started"
    trace_messages = [message for message in messages if message["type"] == "trace"]
    assert any(
        message["trace"]["nodes"][-1]["node_id"] == "done" for message in trace_messages
    )
    terminal = messages[-1]
    assert terminal["type"] == "result"
    assert terminal["result"]["status"] == "completed"
    assert terminal["result"]["waiting"] is None
    assert terminal["result"]["output"]["title"] == "雨中故人"


def _receive_until_terminal(websocket) -> list[dict]:
    messages = []
    while True:
        message = websocket.receive_json()
        messages.append(message)
        if message["type"] in {"result", "error"}:
            return messages


class FakeRouteBackend:
    name = "fake-route-pro"

    def __init__(self) -> None:
        from test_creation_graph_pro import _PAYLOADS

        self.payloads = _PAYLOADS

    async def generate_text(
        self, messages, *, model=None, fallbacks=None, response_format=None
    ) -> TextResult:
        import json

        marker = "YTS_PRO_STAGE:"
        content = messages[-1]["content"]
        stage = content.split(marker, 1)[1].splitlines()[0].strip()
        return TextResult(
            text=json.dumps(self.payloads[stage], ensure_ascii=False), provider="fake", model="fake"
        )


class BadJsonBackend:
    name = "bad-json"

    async def generate_text(
        self, messages, *, model=None, fallbacks=None, response_format=None
    ) -> TextResult:
        return TextResult(text="not json", provider="fake", model="fake")
