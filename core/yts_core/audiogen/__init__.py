"""音频生成(流式 PCM 帧)—— 传输无关核心。

统一帧流契约(见 desktop/STREAM_PROTOCOL.md)的云端 producer 实现:
异步产出 mono f32 PCM 帧块。FastAPI WebSocket 路由只是薄入口,调本模块。

本轮云端用确定性合成器(与本地 candle-server 同声学,便于双来源对拍);
真实云端音乐模型(ACE-Step / Stable Audio,GPU)替换 generate_frames() 即可,契约不变。
"""

from .generator import CHANNELS, FORMAT, SAMPLE_RATE, generate_frames, negotiate_channels

__all__ = ["SAMPLE_RATE", "CHANNELS", "FORMAT", "generate_frames", "negotiate_channels"]
