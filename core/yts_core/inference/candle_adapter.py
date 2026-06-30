"""
本地推理适配器:经 HTTP 调 Rust 的 candle-server(desktop/candle-server)。

架构(v3.1):推理在 Rust(Candle)。Python 编排经此适配器 HTTP 调本地 candle-server。
Mac 桌面形态:Tauri 壳可 spawn candle-server;sidecar(Python)与之同机通信。
图片/语音/音乐(SD / Whisper+TTS / MusicGen)为 TODO。
"""

from __future__ import annotations

import httpx

from ..config import get_settings
from .port import TextResult


class CandleInference:
    name = "candle"

    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or get_settings().candle_base_url).rstrip("/")

    async def generate_text(self, messages, *, model=None, fallbacks=None, response_format=None) -> TextResult:
        prompt = messages[-1]["content"] if messages else ""
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{self._base}/candle/text",
                json={
                    "prompt": prompt,
                    "max_tokens": 256,
                    "response_format": response_format,
                },
            )
            r.raise_for_status()
            data = r.json()
        return TextResult(text=data["text"], provider="candle", model=data.get("model", "local"))

    async def generate_image(self, prompt: str) -> bytes:
        raise NotImplementedError("candle image (SD): TODO in candle-server")

    async def generate_speech(self, text: str) -> bytes:
        raise NotImplementedError("candle TTS: TODO in candle-server")

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:
        raise NotImplementedError("candle music (MusicGen): TODO in candle-server")
