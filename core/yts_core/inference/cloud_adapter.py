"""云推理适配器:文本走 LiteLLM;图片/语音/音乐 TODO(云端模型)。"""

from __future__ import annotations

from ..llm.client import complete_text
from .port import TextResult


class CloudInference:
    name = "cloud-litellm"

    async def generate_text(self, messages, *, model=None, fallbacks=None) -> TextResult:
        return await complete_text(messages, model=model, fallbacks=fallbacks)

    async def generate_image(self, prompt: str) -> bytes:  # TODO: 云图像模型
        raise NotImplementedError("cloud image gen: TODO")

    async def generate_speech(self, text: str) -> bytes:  # TODO: 云 TTS
        raise NotImplementedError("cloud TTS: TODO")

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:  # TODO
        raise NotImplementedError("cloud music gen: TODO")
