"""核心可调用 API —— 薄入口(FastAPI / sidecar / 未来 PyO3)只调这里,不写业务。"""
from __future__ import annotations

from ..schemas.common import ExecutionSummary
from ..schemas.creation import (
    CreationRequest,
    CreationResult,
    InspirationRequest,
    InspirationResult,
)
from .creation_graph import build_creation_graph

# 编译一次复用(无 checkpointer 的内存档;持久化档由 server/sidecar 注入后另建)
_GRAPH = build_creation_graph()


async def run_creation(req: CreationRequest, *, backend=None, checkpointer=None) -> CreationResult:
    """运行创作 6 步图。backend/checkpointer 由调用方按 profile 注入(本轮 stub 不强制用)。"""
    graph = _GRAPH if checkpointer is None else build_creation_graph(checkpointer=checkpointer)
    state = await graph.ainvoke({
        "user_prompt": req.user_prompt,
        "music_dimensions": req.music_dimensions,
        "skill_id": req.skill_id,
        "stages": [],
        "retries": 0,
    })
    return CreationResult(
        title=state.get("title", ""),
        lyrics=state.get("lyrics", ""),
        style=state.get("style", ""),
        final_draft=state.get("final_draft", ""),
        summary=ExecutionSummary(
            backend=getattr(backend, "name", "stub"),
            stages=state.get("stages", []),
        ),
    )


async def run_inspiration(req: InspirationRequest, *, backend=None) -> InspirationResult:
    """灵感填充(单步)。本轮 stub;真实实现调 backend.generate_text。"""
    text = f"[stub] inspiration for: {req.current_prompt[:64]}"
    return InspirationResult(
        inspiration=text,
        summary=ExecutionSummary(backend=getattr(backend, "name", "stub")),
    )
