"""
本地推理适配器:经 HTTP 调 Rust 的 **GGML 推理网关**(desktop/infer-gateway,名称兼容保留)。

网关把四模态统一对接 GGML 原生二进制:
- 文本 /text → 代理常驻 llama-server(llama.cpp,OpenAI 兼容)
- 图片 /image → stable-diffusion.cpp
- 音乐 /music/stream → acestep.cpp / 内置合成器
(历史:文本曾用 Candle 内嵌 quantized_llama,已移除。)
"""

from __future__ import annotations

import httpx

from ..config import Settings, get_settings
from .port import TextResult


class GatewayInference:
    name = "gateway"

    def __init__(self, settings: Settings | None = None, base_url: str | None = None) -> None:
        self._settings = settings or get_settings()
        self._base = (base_url or self._settings.gateway_base_url).rstrip("/")

    async def generate_text(
        self, messages, *, model=None, fallbacks=None, response_format=None
    ) -> TextResult:
        prompt = messages[-1]["content"] if messages else ""
        async with httpx.AsyncClient(timeout=self._settings.gateway_request_timeout_seconds) as c:
            r = await c.post(
                f"{self._base}/text",
                json={
                    "prompt": prompt,
                    "max_tokens": self._settings.gateway_text_max_tokens,
                    "response_format": response_format,
                },
            )
            r.raise_for_status()
            data = r.json()
        return TextResult(text=data["text"], provider="gateway", model=data.get("model", "local"))

    async def generate_image(
        self, prompt: str, *, width: int = 512, height: int = 512, steps: int = 20
    ) -> bytes:
        """经 infer-gateway /image 调 stable-diffusion.cpp(或占位 producer)。返回 PNG 字节。"""
        import base64

        async with httpx.AsyncClient(timeout=self._settings.gateway_request_timeout_seconds) as c:
            r = await c.post(
                f"{self._base}/image",
                json={"prompt": prompt, "width": width, "height": height, "steps": steps},
            )
            r.raise_for_status()
            data = r.json()
        return base64.b64decode(data["png_base64"])

    async def generate_speech(self, text: str) -> bytes:
        raise NotImplementedError("TTS: TODO in infer-gateway")

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:
        raise NotImplementedError("music (MusicGen): TODO in infer-gateway")
