from __future__ import annotations

import sys
import types

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START
from typing_extensions import TypedDict
from yts_core.config import Settings
from yts_core.orchestration import service
from yts_core.orchestration.checkpointing import (
    build_langgraph_checkpointer,
    close_langgraph_checkpointer,
    setup_langgraph_checkpointer,
)
from yts_core.orchestration.flow_builder import FlowSpec, build_flow_graph, workflow_config
from yts_core.orchestration.prompt_packs import resolve_prompt_pack
from yts_core.schemas.creation import CreationRequest

LOCAL_POSTGRES_DSN = "postgresql://hongcq:hongcq@127.0.0.1/lss?connect_timeout=5&gssencmode=disable"


class MiniState(TypedDict, total=False):
    value: int


class MiniNodes:
    async def start(self, state: MiniState) -> dict:
        return {"value": 1}

    async def finish(self, state: MiniState) -> dict:
        return {"value": state["value"] + 1}


@pytest.mark.asyncio
async def test_build_flow_graph_uses_declared_nodes_and_edges() -> None:
    graph = build_flow_graph(
        FlowSpec(
            name="mini",
            state_type=MiniState,
            stages=("start", "finish"),
            edges=((START, "start"), ("start", "finish"), ("finish", END)),
        ),
        MiniNodes(),
    )

    state = await graph.ainvoke({})

    assert state["value"] == 2


def test_workflow_config_requires_thread_id_when_checkpointer_is_enabled() -> None:
    with pytest.raises(ValueError, match="thread_id is required"):
        workflow_config(checkpointer=object(), thread_id=None)


def test_workflow_config_trims_thread_and_run_identifiers() -> None:
    assert workflow_config(checkpointer=object(), thread_id=" thread-1 ", run_id=" run-1 ") == {
        "configurable": {"thread_id": "thread-1", "run_id": "run-1"}
    }


def test_build_langgraph_checkpointer_returns_none_when_disabled() -> None:
    close_langgraph_checkpointer()

    checkpointer = build_langgraph_checkpointer(
        Settings(langgraph_checkpoint_backend="disabled")
    )

    assert checkpointer is None


def test_build_langgraph_checkpointer_uses_memory_backend() -> None:
    close_langgraph_checkpointer()

    first = build_langgraph_checkpointer(Settings(langgraph_checkpoint_backend="memory"))
    second = build_langgraph_checkpointer(Settings(langgraph_checkpoint_backend="memory"))
    close_langgraph_checkpointer()

    assert isinstance(first, InMemorySaver)
    assert second is first


def test_default_checkpoint_settings_use_local_postgres() -> None:
    settings = Settings()

    assert settings.langgraph_checkpoint_backend == "postgres"
    assert settings.langgraph_checkpoint_postgres_dsn == LOCAL_POSTGRES_DSN


def test_build_langgraph_checkpointer_uses_local_postgres_dsn(monkeypatch) -> None:
    close_langgraph_checkpointer()
    observed = {}
    postgres_module = types.ModuleType("langgraph.checkpoint.postgres")
    postgres_module.PostgresSaver = FakePostgresSaver
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres", postgres_module)
    FakePostgresSaver.observed = observed

    checkpointer = build_langgraph_checkpointer(Settings())
    close_langgraph_checkpointer()

    assert checkpointer == "postgres-checkpointer"
    assert observed["dsn"] == LOCAL_POSTGRES_DSN


def test_setup_langgraph_checkpointer_runs_postgres_setup(monkeypatch) -> None:
    observed = {}
    postgres_module = types.ModuleType("langgraph.checkpoint.postgres")
    postgres_module.PostgresSaver = FakePostgresSaver
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres", postgres_module)
    FakePostgresSaver.observed = observed

    setup_langgraph_checkpointer(Settings())

    assert observed["dsn"] == LOCAL_POSTGRES_DSN
    assert observed["setup_called"] is True


def test_build_langgraph_checkpointer_rejects_unsupported_backend() -> None:
    close_langgraph_checkpointer()

    with pytest.raises(ValueError, match="unsupported langgraph checkpoint backend"):
        build_langgraph_checkpointer(Settings(langgraph_checkpoint_backend="sqlite"))


@pytest.mark.asyncio
async def test_run_creation_passes_thread_config_to_checkpointed_graph(monkeypatch) -> None:
    graph = FakeGraph()
    checkpointer = object()

    def fake_get_graph(backend, candidate_checkpointer):
        assert backend.name == "fake-runtime"
        assert candidate_checkpointer is checkpointer
        return graph

    monkeypatch.setattr(service, "_get_graph", fake_get_graph)

    await service.run_creation(
        CreationRequest(user_prompt="雨天的歌"),
        backend=FakeBackend(),
        checkpointer=checkpointer,
        thread_id=" thread-1 ",
        run_id=" run-1 ",
    )

    assert graph.config == {"configurable": {"thread_id": "thread-1", "run_id": "run-1"}}
    assert graph.state["user_prompt"] == "雨天的歌"
    assert graph.state["thread_id"] == "thread-1"
    assert graph.state["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_run_creation_generates_run_id_for_runtime_state(monkeypatch) -> None:
    graph = FakeGraph()
    monkeypatch.setattr(service, "_get_graph", lambda backend, checkpointer: graph)

    await service.run_creation(
        CreationRequest(user_prompt="雨天的歌"),
        backend=FakeBackend(),
    )

    assert graph.config is None
    assert graph.state["thread_id"] == ""
    assert graph.state["run_id"].startswith("run-")
    assert len(graph.state["run_id"]) > len("run-")


@pytest.mark.asyncio
async def test_run_creation_uses_request_thread_id_when_argument_is_omitted(monkeypatch) -> None:
    graph = FakeGraph()
    checkpointer = object()
    monkeypatch.setattr(service, "_get_graph", lambda backend, candidate: graph)

    await service.run_creation(
        CreationRequest(user_prompt="雨天的歌", thread_id=" request-thread "),
        backend=FakeBackend(),
        checkpointer=checkpointer,
        run_id="run-request",
    )

    assert graph.state["thread_id"] == "request-thread"
    assert graph.config == {"configurable": {"thread_id": "request-thread", "run_id": "run-request"}}


@pytest.mark.asyncio
async def test_run_creation_rejects_checkpoint_without_thread_id(monkeypatch) -> None:
    called = False

    def fake_get_graph(backend, candidate_checkpointer):
        nonlocal called
        called = True
        return FakeGraph()

    monkeypatch.setattr(service, "_get_graph", fake_get_graph)

    with pytest.raises(ValueError, match="thread_id is required"):
        await service.run_creation(
            CreationRequest(user_prompt="雨天的歌"),
            backend=FakeBackend(),
            checkpointer=object(),
        )

    assert called is False


@pytest.mark.asyncio
async def test_checkpointed_creation_graph_persists_by_thread_id() -> None:
    checkpointer = InMemorySaver()
    graph = service.build_creation_graph(backend=CheckpointBackend(), checkpointer=checkpointer)
    config = workflow_config(checkpointer=checkpointer, thread_id="thread-persist", run_id="run-persist")

    state = await graph.ainvoke(
        {
            "user_prompt": "雨天的歌",
            "music_dimensions": {},
            "skill_id": None,
            "thread_id": "thread-persist",
            "run_id": "run-persist",
            "prompt_pack": resolve_prompt_pack("pro_lyrics").to_state(),
            "stages": [],
            "retries": 0,
        },
        config=config,
    )

    checkpoint = checkpointer.get_tuple({"configurable": {"thread_id": "thread-persist"}})
    assert checkpoint is not None
    assert state["title"] == "雨中故人"
    assert checkpoint.config["configurable"]["thread_id"] == "thread-persist"


class FakeBackend:
    name = "fake-runtime"


class FakeGraph:
    def __init__(self) -> None:
        self.state = None
        self.config = None

    async def ainvoke(self, state, config=None):
        self.state = state
        self.config = config
        return {
            **state,
            "title": "标题",
            "lyrics": "歌词",
            "style": "风格",
            "final_draft": "成稿",
            "stages": [],
        }


class CheckpointBackend:
    name = "checkpoint-backend"

    async def generate_text(self, messages, *, model=None, fallbacks=None, response_format=None):
        from test_creation_graph_pro import _FakeProBackend

        if not hasattr(self, "_backend"):
            self._backend = _FakeProBackend()
        return await self._backend.generate_text(
            messages,
            model=model,
            fallbacks=fallbacks,
            response_format=response_format,
        )


class FakePostgresSaver:
    observed = {}

    @classmethod
    def from_conn_string(cls, dsn):
        cls.observed["dsn"] = dsn
        return cls()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def setup(self):
        self.observed["setup_called"] = True

    def __eq__(self, other):
        return other == "postgres-checkpointer"
