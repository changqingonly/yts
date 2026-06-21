"""创作 / 灵感 API 契约。语义参考 yuetools creation-core(6 步 composition)。"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .common import ExecutionSummary


class LyricsMode(str, Enum):
    AUTO = "auto"
    SPLIT = "split"  # 分段降级(lyrics rescue)


class CreationRequest(BaseModel):
    user_prompt: str
    music_dimensions: dict[str, str] = Field(default_factory=dict)  # 12 维约束
    lyrics_mode: LyricsMode = LyricsMode.AUTO
    persist: bool = True
    llm_override: str | None = None      # 强制 provider/model
    skill_id: str | None = None          # 自定义 skill(仅本地实现支持)


class CreationResult(BaseModel):
    title: str = ""
    lyrics: str = ""
    style: str = ""
    final_draft: str = ""
    summary: ExecutionSummary = Field(default_factory=ExecutionSummary)


class InspirationRequest(BaseModel):
    current_prompt: str
    llm_override: str | None = None
    skill_id: str | None = None


class InspirationResult(BaseModel):
    inspiration: str = ""
    summary: ExecutionSummary = Field(default_factory=ExecutionSummary)
