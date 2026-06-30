"""
按配置选择推理后端(端口-适配器的装配点)。

YTS_INFERENCE_BACKEND = echo | cloud | openai | candle | pro-fixture
- echo  :确定性,默认,无依赖(验证/离线)
- cloud :LiteLLM 云模型(需 provider 凭据,允许显式 fallbacks)
- openai:OpenAI-compatible text model via configured api key,不做隐式降级
- candle:本地 Rust Candle(经 candle_base_url 的 HTTP 桥)
- pro-fixture:显式本地演示后端,返回 Pro 流程严格 JSON
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
    
    if kind == "openai":
        from .openai_adapter import OpenAIInference
        return OpenAIInference(settings)
    
    if kind == "candle":
        from .candle_adapter import CandleInference
        return CandleInference()
    
    if kind == "pro-fixture":
        from .pro_fixture_adapter import ProFixtureBackend
        return ProFixtureBackend()
    
    if kind == "echo":
        from .echo_adapter import EchoBackend
        return EchoBackend()
    
    raise ValueError(f"Unsupported inference backend: {kind}")
