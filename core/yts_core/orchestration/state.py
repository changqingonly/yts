from __future__ import annotations

from typing import TypedDict

from ..schemas.common import StageTrace


class CreationState(TypedDict, total=False):
    """Pro 创作管道的共享状态(LangGraph StateGraph)。"""

    user_prompt: str
    music_dimensions: dict[str, str]
    skill_id: str | None
    # 对外结果字段
    analysis: str
    structure: str
    lyrics: str
    style: str
    final_draft: str
    title: str
    # Pro 制作人流程内部产物
    intent: dict
    song_brief: dict
    hook_lab: dict
    structure_blueprints: dict
    structure_critique: dict
    professional_plan: dict
    structure_plan: dict
    style_spec: dict
    generation: dict
    quality_review: dict
    title_refinement: dict
    # 控制 + 轨迹
    retry: bool
    retries: int
    stages: list[StageTrace]
