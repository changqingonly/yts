"""核心可调用 API —— 薄入口(FastAPI / sidecar / 未来 PyO3)只调这里,不写业务。"""

from __future__ import annotations

from uuid import uuid4

from ..inference import make_backend
from ..schemas.common import ExecutionSummary
from ..schemas.creation import (
    CreationRequest,
    CreationResult,
    InspirationRequest,
    InspirationResult,
)
from .creation_graph import build_creation_graph
from .flow_builder import workflow_config
from .prompt_packs import resolve_prompt_pack

# 按 backend 实例缓存无 checkpointer 的 Pro 创作图(避免每请求重编译)。
# 带 checkpointer 的图依赖外部持久化实例,不放入进程级缓存。
_graph_cache: dict[tuple[str, int], object] = {}


def _get_graph(backend, checkpointer):
    if checkpointer is not None:
        return build_creation_graph(backend=backend, checkpointer=checkpointer)
    cache_key = (backend.name, id(backend))
    g = _graph_cache.get(cache_key)
    if g is None:
        g = build_creation_graph(backend=backend)
        _graph_cache[cache_key] = g
    return g


async def run_creation(
    req: CreationRequest,
    *,
    backend=None,
    checkpointer=None,
    thread_id: str | None = None,
    run_id: str | None = None,
    checkpoint_ns: str | None = None,
    checkpoint_id: str | None = None,
) -> CreationResult:
    """运行 Pro 创作图。checkpoint 模式必须提供 LangGraph thread_id。"""

    backend = backend or make_backend()
    runtime_thread_id = _runtime_thread_id(thread_id if thread_id is not None else req.thread_id)
    runtime_run_id = _runtime_run_id(run_id)
    checkpoint_context_requested = (
        checkpointer is not None or checkpoint_ns is not None or checkpoint_id is not None
    )
    config = workflow_config(
        checkpointer=checkpointer,
        thread_id=runtime_thread_id or None,
        run_id=runtime_run_id if checkpoint_context_requested or runtime_thread_id else None,
        checkpoint_ns=checkpoint_ns,
        checkpoint_id=checkpoint_id,
    )
    graph = _get_graph(backend, checkpointer)
    prompt_pack = resolve_prompt_pack("pro_lyrics").to_state()
    initial_state = {
        "user_prompt": req.user_prompt,
        "music_dimensions": req.music_dimensions,
        "skill_id": req.skill_id,
        "thread_id": runtime_thread_id,
        "run_id": runtime_run_id,
        "prompt_pack": prompt_pack,
        "stages": [],
        "retries": 0,
    }
    state = await graph.ainvoke(initial_state, config=config)
    return CreationResult(
        title=state.get("title", ""),
        lyrics=state.get("lyrics", ""),
        style=state.get("style", ""),
        final_draft=state.get("final_draft", ""),
        summary=ExecutionSummary(
            backend=backend.name,
            prompt_pack=state["prompt_pack"],
            stages=state.get("stages", []),
        ),
    )


def _runtime_thread_id(thread_id: str | None) -> str:
    if thread_id is None:
        return ""
    return thread_id.strip()


def _runtime_run_id(run_id: str | None) -> str:
    if run_id is None:
        return f"run-{uuid4().hex}"
    value = run_id.strip()
    if not value:
        raise ValueError("run_id must not be empty")
    return value


async def run_inspiration(req: InspirationRequest, *, backend=None) -> InspirationResult:
    """灵感填充(单步):直接调推理后端。"""
    backend = backend or make_backend()
    r = await backend.generate_text(
        [{"role": "user", "content": f"基于当前想法给一句创作灵感:\n{req.current_prompt}"}]
    )
    return InspirationResult(
        inspiration=r.text,
        summary=ExecutionSummary(backend=backend.name, provider=r.provider, model=r.model),
    )
