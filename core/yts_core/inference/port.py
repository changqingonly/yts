"""推理后端抽象端口(ports & adapters)。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TextResult:
    text: str
    provider: str
    model: str


@runtime_checkable
class InferenceBackend(Protocol):
    """文本/图片/语音/背景音乐统一推理端口。

    cloud 实现走 LiteLLM;local 实现走 Candle(经 Rust)。
    图片/语音/音乐先以字节 bytes 占位返回。
    """

    name: str

    async def generate_text(
        self, messages: list[dict], *, model: str | None = None, fallbacks: list[str] | None = None
    ) -> TextResult: ...

    async def generate_image(self, prompt: str) -> bytes: ...

    async def generate_speech(self, text: str) -> bytes: ...

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes: ...
