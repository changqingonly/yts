from __future__ import annotations

import logging
from pathlib import Path

from yts_core.config import Settings
from yts_server.logging_config import configure_logging

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_structlog_is_declared_for_server_and_core() -> None:
    for path in ["server/pyproject.toml", "core/pyproject.toml"]:
        source = read(path)
        assert '"structlog==26.1.0",' in source


def test_server_configures_structured_logging_on_app_creation() -> None:
    main = read("server/yts_server/main.py")
    logging_config = read("server/yts_server/logging_config.py")

    assert "from .logging_config import configure_logging" in main
    assert "configure_logging(settings)" in main
    assert "structlog.configure(" in logging_config
    assert "structlog.stdlib.ProcessorFormatter" in logging_config
    assert "JSONRenderer" in logging_config
    assert "ConsoleRenderer" in logging_config


def test_logging_config_uses_level_from_settings() -> None:
    configure_logging(Settings(logging_level="DEBUG", logging_format="console"))

    assert logging.getLogger().level == logging.DEBUG


def test_logging_config_rejects_unknown_level() -> None:
    settings = Settings(logging_level="LOUD", logging_format="console")

    try:
        configure_logging(settings)
    except ValueError as exc:
        assert "unsupported logging level: LOUD" in str(exc)
    else:
        raise AssertionError("configure_logging should reject unsupported logging level")


def test_workflow_route_logs_request_lifecycle_with_structlog() -> None:
    source = read("server/yts_server/routes/workflow.py")

    assert "import structlog" in source
    assert "logger = structlog.get_logger(__name__)" in source
    for event in [
        '"workflow.run.requested"',
        '"workflow.run.completed"',
        '"workflow.run.failed"',
        '"workflow.resume.requested"',
        '"workflow.resume.completed"',
        '"workflow.resume.failed"',
        '"workflow.trace.requested"',
        '"workflow.trace.completed"',
    ]:
        assert event in source
    for field in [
        "workflow_id=workflow_id",
        "thread_id=req.thread_id",
        "prompt_chars=len(req.user_prompt)",
        "node_config_keys=sorted(req.node_config)",
        "waiting_node_id=result.waiting.node_id if result.waiting else None",
        "trace_node_count=len(result.trace.nodes)",
    ]:
        assert field in source


def test_workflow_runtime_logs_node_and_hitl_lifecycle() -> None:
    source = read("core/yts_core/workflow/runtime.py")

    assert "import structlog" in source
    assert "logger = structlog.get_logger(__name__)" in source
    for event in [
        '"workflow.thread.started"',
        '"workflow.thread.completed"',
        '"workflow.thread.failed"',
        '"workflow.thread.resume_requested"',
        '"workflow.thread.resume_completed"',
        '"workflow.node.started"',
        '"workflow.node.completed"',
        '"workflow.node.failed"',
        '"workflow.hitl.waiting"',
        '"workflow.hitl.decision"',
    ]:
        assert event in source
    for field in [
        "workflow_id=request.workflow_id",
        "thread_id=request.thread_id.strip()",
        'run_id=state["run_id"]',
        "node_id=node.id",
        "stage=stage",
        "duration_ms=duration_ms",
    ]:
        assert field in source


def test_pro_lyrics_and_llm_client_log_llm_boundaries_without_full_payloads() -> None:
    nodes = read("core/yts_core/orchestration/nodes/pro_lyrics.py")
    client = read("core/yts_core/llm/client.py")

    assert "import structlog" in nodes
    assert "logger = structlog.get_logger(__name__)" in nodes
    for event in [
        '"pro_lyrics.llm.requested"',
        '"pro_lyrics.llm.completed"',
        '"pro_lyrics.llm.invalid_json"',
        '"pro_lyrics.llm.invalid_shape"',
    ]:
        assert event in nodes
    for field in [
        "stage=stage",
        "payload_keys=sorted(payload)",
        'prompt_pack_version=prompt_pack.get("version")',
        "duration_ms=duration_ms",
        "response_chars=len(response.text)",
    ]:
        assert field in nodes
    assert "payload=payload" not in nodes
    assert "messages=messages" not in nodes

    assert "import structlog" in client
    assert "logger = structlog.get_logger(__name__)" in client
    for event in [
        '"llm.litellm.requested"',
        '"llm.litellm.completed"',
        '"llm.litellm.failed"',
    ]:
        assert event in client
    for field in [
        "message_count=len(messages)",
        "duration_ms=duration_ms",
        "error_type=type(exc).__name__",
    ]:
        assert field in client
    assert '"llm.openai.' not in client
    assert "api_key=api_key" not in client
