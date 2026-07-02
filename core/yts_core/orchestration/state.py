from __future__ import annotations

from typing import TypedDict


class CreationState(TypedDict, total=False):
    """Pro 创作管道的共享状态(LangGraph StateGraph)。"""

    user_prompt: str
    music_dimensions: dict[str, str]
    skill_id: str | None
    thread_id: str
    run_id: str
    prompt_pack: dict[str, str]
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
    style_template_candidates: list[dict]
    music_style_plan: dict
    hook_lab: dict
    structure_blueprints: dict
    structure_critique: dict
    professional_plan: dict
    structure_plan: dict
    style_spec: dict
    generation: dict
    quality_review: dict
    title_refinement: dict
    llm_calls: dict[str, dict]
    # 控制 + 轨迹
    retry: bool
    retries: int
    stages: list[dict]
