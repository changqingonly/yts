"""按配置选择推理后端(端口-适配器的装配点)。

YTS_INFERENCE_BACKEND = echo | cloud | candle
- echo  :确定性,默认,无依赖(验证/离线)
- cloud :LiteLLM 云模型(需 provider 凭据)
- candle:本地 Rust Candle(经 candle_base_url 的 HTTP 桥)
"""

from __future__ import annotations

from ..config import Settings, get_settings
from .port import InferenceBackend


def make_backend(settings: Settings | None = None) -> InferenceBackend:
    settings = settings or get_settings()
    kind = settings.inference_backend
    if kind == "cloud":
        from .cloud_adapter import CloudInference

        return CloudInference()
    if kind == "candle":
        from .candle_adapter import CandleInference

        return CandleInference()
    from .echo_adapter import EchoBackend

    return EchoBackend()
