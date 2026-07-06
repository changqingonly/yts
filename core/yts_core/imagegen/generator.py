"""云端图像生成(传输无关)。返回 PNG 字节。

本轮:占位 PNG(纯 Python zlib,无第三方依赖),随 prompt 变色的对角渐变,
与本地 infer-gateway 的占位一致,便于双源对拍。

★ 真实云端模型替换点:generate_png 内改为调云图模型/服务(FLUX/SD3.5/Qwen-Image),
返回其 PNG 字节即可;上层契约(prompt/width/height/steps → PNG)不变。
"""

from __future__ import annotations

import asyncio
import struct
import zlib


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _placeholder_png(prompt: str, width: int, height: int) -> bytes:
    w = max(16, min(width, 2048))
    h = max(16, min(height, 2048))
    seed = 0
    for b in prompt.encode("utf-8"):
        seed = (seed * 31 + b) & 0xFFFFFFFF
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # 每行 filter byte = 0
        for x in range(w):
            r = ((x * 255 // w) ^ (seed & 0xFF)) & 0xFF
            g = ((y * 255 // h) + ((seed >> 8) & 0xFF)) & 0xFF
            b = (((x + y) * 255 // (w + h)) ^ ((seed >> 16) & 0xFF)) & 0xFF
            raw += bytes([r, g, b])
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _png_chunk(b"IEND", b"")
    )


async def generate_png(
    prompt: str, *, width: int = 512, height: int = 512, steps: int = 20
) -> bytes:
    """生成 PNG 字节(占位)。CPU 编码放线程池避免阻塞事件循环。"""
    return await asyncio.to_thread(_placeholder_png, prompt, width, height)
