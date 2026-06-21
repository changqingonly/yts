"""运行配置(pydantic-settings)。区分 cloud / local 两个 profile。

- cloud:服务端,云 LLM + Postgres + 计费 + Phoenix。
- local:桌面 sidecar,Candle 推理 + SQLite + 自定义 skill + 免计费。
"""
from __future__ import annotations

from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(str, Enum):
    CLOUD = "cloud"
    LOCAL = "local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YTS_", env_file=".env", extra="ignore")

    profile: Profile = Profile.CLOUD

    # 数据库:cloud=Postgres(asyncpg) / local=SQLite
    database_url: str = "postgresql+asyncpg://localhost/yts"

    # 推理后端:cloud 用 LiteLLM 云模型;local 用 Candle(经 Rust)
    default_text_model: str = "deepseek/deepseek-chat"
    model_fallbacks: list[str] = Field(default_factory=lambda: ["openai/qwen-max"])

    # 本地推理桥(Mac sidecar → Tauri 进程的 Candle endpoint)
    candle_base_url: str = "http://127.0.0.1:8765"

    # 能力开关(随 profile 默认)
    allow_custom_skills: bool = False  # 仅 local 置 True
    billing_enabled: bool = True       # 仅 cloud 置 True

    # Phoenix 评估/可观测(仅 cloud)
    phoenix_enabled: bool = False

    def for_local(self) -> "Settings":
        """返回本地档覆盖(桌面 sidecar 用)。"""
        return self.model_copy(update={
            "profile": Profile.LOCAL,
            "database_url": "sqlite+aiosqlite:///./yts_local.db",
            "allow_custom_skills": True,
            "billing_enabled": False,
            "phoenix_enabled": False,
        })


def get_settings() -> Settings:
    return Settings()
