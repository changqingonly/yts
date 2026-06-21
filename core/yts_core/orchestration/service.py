"""核心可调用 API —— 薄入口(FastAPI / sidecar / 未来 PyO3)只调这里,不写业务。"""

from __future__ import annotations

from ..inference import make_backend
from ..schemas.common import ExecutionSummary
from ..schemas.creation import (
    CreationRequest,
    CreationResult,
    InspirationRequest,
    InspirationResult,
)
from .creation_graph import build_creation_graph

# 按 backend 名缓存无 checkpointer 的内存图(避免每请求重编译)
_graph_cache: dict[str, object] = {}


def _get_graph(backend, checkpointer):
    if checkpointer is not None:
        return build_creation_graph(backend=backend, checkpointer=checkpointer)
    g = _graph_cache.get(backend.name)
    if g is None:
        g = build_creation_graph(backend=backend)
        _graph_cache[backend.name] = g
    return g


async def run_creation(req: CreationRequest, *, backend=None, checkpointer=None) -> CreationResult:
    """运行创作 6 步图。backend 默认按配置选择(echo/cloud/candle)。"""
    backend = backend or make_backend()
    graph = _get_graph(backend, checkpointer)
    state = await graph.ainvoke(
        {
            "user_prompt": req.user_prompt,
            "music_dimensions": req.music_dimensions,
            "skill_id": req.skill_id,
            "stages": [],
            "retries": 0,
        }
    )
    return CreationResult(
        title=state.get("title", ""),
        lyrics=state.get("lyrics", ""),
        style=state.get("style", ""),
        final_draft=state.get("final_draft", ""),
        summary=ExecutionSummary(backend=backend.name, stages=state.get("stages", [])),
    )


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
