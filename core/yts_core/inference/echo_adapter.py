"""
Echo 推理后端:确定性、无需任何凭据/模型。

用于:① 默认后端,使编排可离线端到端验证(产出由 prompt 派生的真实文本,非 [stub]);
② 单测 baseline。生产切 cloud(LiteLLM)或 candle(本地 Rust)。
"""

from __future__ import annotations

from .port import TextResult


class EchoBackend:
    name = "echo"

    async def generate_text(
        self, messages, *, model=None, fallbacks=None, response_format=None
    ) -> TextResult:
        last = messages[-1]["content"] if messages else ""
        return TextResult(text=f"〔echo〕{last}", provider="echo", model="echo")

    async def generate_image(self, prompt: str) -> bytes:
        raise NotImplementedError("echo backend: image not supported")

    async def generate_speech(self, text: str) -> bytes:
        raise NotImplementedError("echo backend: speech not supported")

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:
        raise NotImplementedError("echo backend: music not supported")
