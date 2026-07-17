"""云端 /music/stream —— 与本地 infer-gateway 同契约的 WebSocket 端点(薄入口)。

消息序列见 desktop/STREAM_PROTOCOL.md:start → header → 二进制 PCM 帧 → end;client 可发 stop。
业务在 yts_core.audiogen;此路由只做 WS 收发 + 取消信号转发。
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from yts_core.audiogen import FORMAT, SAMPLE_RATE, generate_frames, negotiate_channels
from yts_core.config import get_settings

from ..db.session import get_sessionmaker
from ..errors import AppError
from .billing_guard import GenerationBillingGuard, billing_user_if_required

router = APIRouter(tags=["music-stream"])


@router.websocket("/music/stream")
async def music_stream(ws: WebSocket) -> None:
    origin = ws.headers.get("origin")
    if origin and origin not in get_settings().server_allowed_origins:
        await ws.close(code=1008, reason="origin not allowed")
        return
    await ws.accept()
    stop = asyncio.Event()

    # 等待 start
    try:
        first = await ws.receive_text()
        msg = json.loads(first)
    except (WebSocketDisconnect, json.JSONDecodeError):
        await ws.close()
        return
    if msg.get("type") != "start":
        await ws.send_text(json.dumps({"type": "error", "message": "expected start"}))
        await ws.close()
        return

    prompt = msg.get("prompt", "")
    seconds = float(msg.get("seconds", 8.0))
    if not prompt or len(prompt) > 4000 or seconds <= 0 or seconds > 60:
        await ws.send_text(json.dumps({"type": "error", "message": "invalid stream request"}))
        await ws.close()
        return
    channels = negotiate_channels(msg.get("accept"))

    async with get_sessionmaker()() as session:
        try:
            user = await billing_user_if_required(
                session, msg.get("authorization"), ws.cookies.get("yts-device")
            )
        except AppError as exc:
            await ws.send_text(
                json.dumps({"type": "error", "code": exc.code, "message": exc.message})
            )
            await ws.close()
            return
        async with GenerationBillingGuard(
            session=session,
            user=user,
            request_id=f"music-stream:{id(ws)}",
            credit_scene="music",
            usage_scene=None,
        ):
            await _stream_audio(ws, prompt, seconds, channels, stop)


async def _stream_audio(
    ws: WebSocket, prompt: str, seconds: float, channels: int, stop: asyncio.Event
) -> None:

    # 后台监听 stop(与帧推送并行)
    async def watch_stop() -> None:
        try:
            while True:
                txt = await ws.receive_text()
                if json.loads(txt).get("type") == "stop":
                    stop.set()
                    return
        except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
            stop.set()

    watcher = asyncio.create_task(watch_stop())

    await ws.send_text(
        json.dumps(
            {"type": "header", "sampleRate": SAMPLE_RATE, "channels": channels, "format": FORMAT}
        )
    )

    frames = 0
    interleaved = 0
    try:
        async for chunk in generate_frames(prompt, seconds, channels=channels, stop=stop):
            await ws.send_bytes(chunk)
            frames += 1
            interleaved += len(chunk) // 4  # f32 = 4 bytes
    except WebSocketDisconnect:
        watcher.cancel()
        return

    # samples = 每声道采样数(与契约一致)
    samples = interleaved // channels
    await ws.send_text(json.dumps({"type": "end", "frames": frames, "samples": samples}))
    watcher.cancel()
    await ws.close()
