"""OpenAI-compatible text inference adapter."""

from __future__ import annotations

from ..config import Settings, get_settings
from ..llm.client import complete_openai_text
from .port import TextResult


class OpenAIInference:
    name = "openai"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def generate_text(
        self, messages, *, model=None, fallbacks=None, response_format=None
    ) -> TextResult:
        if fallbacks:
            raise ValueError("openai backend does not support implicit model fallbacks")
        return await complete_openai_text(
            messages,
            settings=self._settings,
            model=model,
            response_format=response_format,
        )

    async def generate_image(self, prompt: str) -> bytes:
        raise NotImplementedError("openai backend: image not supported")

    async def generate_speech(self, text: str) -> bytes:
        raise NotImplementedError("openai backend: speech not supported")

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:
        raise NotImplementedError("openai backend: music not supported")
