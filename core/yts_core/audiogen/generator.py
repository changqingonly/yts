"""云端流式 PCM 帧生成器(传输无关)。契约:f32le @ 48k mono。

generate_frames 是 async generator,逐块 yield Float32 bytes(little-endian),
配合 asyncio.sleep 模拟生成/播放节奏。FastAPI WS 路由消费它并推给前端。

★ 真实云端模型替换点:把 _synth_chunk 换成模型逐段解码出的 PCM(整段→分块 yield)。
"""

from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import AsyncIterator

SAMPLE_RATE = 48_000
CHANNELS = 1
FORMAT = "f32le"
_CHUNK_SAMPLES = 4_800  # 100ms @ 48k


def _seed(prompt: str) -> int:
    h = 1469598103934665603
    for b in prompt.encode("utf-8"):
        h = ((h ^ b) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def _synth_chunk(seed: int, start: int, n: int) -> bytes:
    base = 220.0 + (seed % 12) * 17.0
    buf = bytearray()
    for i in range(n):
        t = (start + i) / SAMPLE_RATE
        env = max(0.0, min(1.0, 1.0 - ((t * 0.5) % 1.0)))
        s = math.sin(2 * math.pi * base * t) * 0.5 + math.sin(2 * math.pi * base * 2 * t) * 0.2
        buf += struct.pack("<f", s * env * 0.3)
    return bytes(buf)


def negotiate_channels(accept: dict | None) -> int:
    """据 client accept 协商声道(1/2,默认 1)。"""
    if accept and accept.get("channels") == 2:
        return 2
    return 1


async def generate_frames(
    prompt: str,
    seconds: float = 8.0,
    *,
    channels: int = 1,
    stop: asyncio.Event | None = None,
) -> AsyncIterator[bytes]:
    """逐块产出 PCM 帧(bytes)。channels=2 时 LRLR 交错(本轮双声道同源)。stop 置位则提前结束。"""
    total = int(max(0.1, seconds) * SAMPLE_RATE)
    seed = _seed(prompt)
    produced = 0
    while produced < total:
        if stop is not None and stop.is_set():
            break
        n = min(_CHUNK_SAMPLES, total - produced)
        chunk = _synth_chunk(seed, produced, n)
        if channels == 2:
            chunk = _to_stereo(chunk)
        yield chunk
        produced += n
        await asyncio.sleep(0.08)  # ≈实时速率


def _to_stereo(mono_bytes: bytes) -> bytes:
    """mono f32le → LRLR 交错立体声。"""
    out = bytearray()
    for i in range(0, len(mono_bytes), 4):
        s = mono_bytes[i : i + 4]
        out += s
        out += s
    return bytes(out)
