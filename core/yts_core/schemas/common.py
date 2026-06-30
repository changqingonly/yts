from __future__ import annotations

from pydantic import BaseModel, Field


class StageTrace(BaseModel):
    """单个编排节点的执行轨迹(对应 LangGraph 一个 node)。"""

    name: str
    ok: bool = True
    elapsed_ms: int = 0
    note: str | None = None


class ExecutionSummary(BaseModel):
    """一次编排执行的元数据。"""

    provider: str | None = None
    model: str | None = None
    backend: str = "stub"  # candle | cloud-litellm | stub
    billed: bool = False
    prompt_pack: dict[str, str] = Field(default_factory=dict)
    stages: list[StageTrace] = Field(default_factory=list)
