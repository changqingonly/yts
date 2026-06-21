"""本地推理适配器:经 Rust 进程的 Candle。

桌面 Mac 形态:Python sidecar 与 Candle(Tauri/Rust 进程)分属两进程,
故经本地 HTTP/IPC 回到 Tauri 进程调用 Candle。Windows in-process 形态(留后)
则可由 PyO3 同进程直调。

本轮为 stub:仅给出调用形状,真实模型加载在 Rust 侧(见 desktop/src-tauri/src/inference)。
"""

from __future__ import annotations

from ..config import get_settings
from .port import TextResult


class CandleInference:
    name = "candle"

    def __init__(self, base_url: str | None = None) -> None:
        self._base = base_url or get_settings().candle_base_url

    async def generate_text(self, messages, *, model=None, fallbacks=None) -> TextResult:
        # TODO: POST {self._base}/candle/text -> Rust(Candle)推理
        last = messages[-1]["content"] if messages else ""
        return TextResult(
            text=f"[candle-stub] {last[:64]}", provider="candle", model=model or "qwen3-local"
        )

    async def generate_image(self, prompt: str) -> bytes:  # TODO: Candle SD
        raise NotImplementedError("candle image (SD): TODO via Rust")

    async def generate_speech(self, text: str) -> bytes:  # TODO: Candle Parler/MetaVoice
        raise NotImplementedError("candle TTS: TODO via Rust")

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:  # TODO: MusicGen
        raise NotImplementedError("candle music (MusicGen): TODO via Rust")
