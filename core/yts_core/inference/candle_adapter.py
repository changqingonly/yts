"""
本地推理适配器:经 HTTP 调 Rust 的 candle-server(desktop/candle-server)。

架构(v3.1):推理在 Rust(Candle)。Python 编排经此适配器 HTTP 调本地 candle-server。
Mac 桌面形态:Tauri 壳可 spawn candle-server;sidecar(Python)与之同机通信。
图片/语音/音乐(SD / Whisper+TTS / MusicGen)为 TODO。
"""

from __future__ import annotations

import httpx

from ..config import Settings, get_settings
from .port import TextResult


class CandleInference:
    name = "candle"

    def __init__(self, settings: Settings | None = None, base_url: str | None = None) -> None:
        self._settings = settings or get_settings()
        self._base = (base_url or self._settings.candle_base_url).rstrip("/")

    async def generate_text(
        self, messages, *, model=None, fallbacks=None, response_format=None
    ) -> TextResult:
        prompt = messages[-1]["content"] if messages else ""
        async with httpx.AsyncClient(timeout=self._settings.candle_request_timeout_seconds) as c:
            r = await c.post(
                f"{self._base}/candle/text",
                json={
                    "prompt": prompt,
                    "max_tokens": self._settings.candle_text_max_tokens,
                    "response_format": response_format,
                },
            )
            r.raise_for_status()
            data = r.json()
        return TextResult(text=data["text"], provider="candle", model=data.get("model", "local"))

    async def generate_image(
        self, prompt: str, *, width: int = 512, height: int = 512, steps: int = 20
    ) -> bytes:
        """经 candle-server /image 调 stable-diffusion.cpp(或占位 producer)。返回 PNG 字节。"""
        import base64

        async with httpx.AsyncClient(timeout=self._settings.candle_request_timeout_seconds) as c:
            r = await c.post(
                f"{self._base}/image",
                json={"prompt": prompt, "width": width, "height": height, "steps": steps},
            )
            r.raise_for_status()
            data = r.json()
        return base64.b64decode(data["png_base64"])

    async def generate_speech(self, text: str) -> bytes:
        raise NotImplementedError("candle TTS: TODO in candle-server")

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:
        raise NotImplementedError("candle music (MusicGen): TODO in candle-server")
