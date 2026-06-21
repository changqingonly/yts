"""推理端口与适配器。core 只依赖 InferenceBackend 协议;具体后端按 profile 注入。

- cloud:CloudInference(LiteLLM 云模型)
- local:CandleInference(经 Rust 进程的 Candle,文本/图片/语音/音乐)
"""

from .port import InferenceBackend, TextResult

__all__ = ["InferenceBackend", "TextResult"]
