"""
按配置选择推理后端(端口-适配器的装配点)。

产品配置只暴露 YTS_INFERENCE_BACKEND = local | cloud:
- local:本地 Rust Candle(经 candle_base_url 的 HTTP 桥)
- cloud:LiteLLM 云模型(DeepSeek/OpenAI 等 provider 由模型名与 provider 配置决定)
"""

from __future__ import annotations

from ..config import Settings, get_settings
from .port import InferenceBackend


def make_backend(settings: Settings | None = None) -> InferenceBackend:
    settings = settings or get_settings()
    kind = settings.inference_backend
    if kind == "local":
        from .candle_adapter import CandleInference

        return CandleInference(settings)

    if kind == "cloud":
        from .cloud_adapter import CloudInference

        return CloudInference(settings)

    raise ValueError(f"Unsupported inference backend: {kind}")
