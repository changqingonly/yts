"""推理端口与适配器。core 只依赖 InferenceBackend 协议;具体后端按配置注入。

产品配置只暴露 local/cloud:
- local:GatewayInference(经 Rust GGML 网关:文本 llama.cpp / 图片 sd.cpp / 音乐 acestep.cpp)
- cloud:CloudInference(LiteLLM 云模型)
"""

from __future__ import annotations

from .factory import make_backend
from .port import InferenceBackend, TextResult

__all__ = ["InferenceBackend", "TextResult", "make_backend"]
