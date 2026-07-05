"""推理端口与适配器。core 只依赖 InferenceBackend 协议;具体后端按配置注入。

产品配置只暴露 local/cloud:
- local:CandleInference(经 Rust 进程的 Candle,文本/图片/语音/音乐)
- cloud:CloudInference(LiteLLM 云模型)
"""

from __future__ import annotations

from .factory import make_backend
from .port import InferenceBackend, TextResult

__all__ = ["InferenceBackend", "TextResult", "make_backend"]
