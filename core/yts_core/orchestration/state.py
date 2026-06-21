from __future__ import annotations

from typing import TypedDict

from ..schemas.common import StageTrace


class CreationState(TypedDict, total=False):
    """创作 6 步管道的共享状态(LangGraph StateGraph)。"""
    user_prompt: str
    music_dimensions: dict[str, str]
    skill_id: str | None
    # 各步产物
    analysis: str
    structure: str
    lyrics: str
    style: str
    final_draft: str
    title: str
    # 控制 + 轨迹
    retry: bool
    retries: int
    stages: list[StageTrace]
