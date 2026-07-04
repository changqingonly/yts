from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

router = APIRouter(prefix="/transport", tags=["transport"])

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


class TransportRpcMessage(BaseModel):
    id: str
    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None


@router.websocket("/rpc")
async def transport_rpc(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            message = TransportRpcMessage.model_validate(await websocket.receive_json())
            await websocket.send_json(await _proxy_rpc_message(websocket, message))
    except WebSocketDisconnect:
        return
    finally:
        await _close_websocket(websocket)


async def _proxy_rpc_message(websocket: WebSocket, message: TransportRpcMessage) -> dict:
    method = message.method.upper()
    if method not in _ALLOWED_METHODS:
        return _error_response(message.id, 405, f"unsupported transport method: {message.method}")
    if not (message.path.startswith("/api/") or message.path == "/health"):
        return _error_response(message.id, 400, f"unsupported transport path: {message.path}")

    headers = {name: value for name, value in message.headers.items() if value}
    app = websocket.scope["app"]
    response = await _dispatch_asgi_request(app, method, message.path, headers, message.body)
    return {
        "id": message.id,
        "status": response["status"],
        "headers": {"content-type": response["content_type"]},
        "body": response["body"],
    }


def _error_response(message_id: str, status: int, detail: str) -> dict:
    return {
        "id": message_id,
        "status": status,
        "headers": {"content-type": "application/json"},
        "body": {"detail": detail},
    }


async def _close_websocket(websocket: WebSocket) -> None:
    try:
        await websocket.close()
    except RuntimeError:
        return


async def _dispatch_asgi_request(
    app,
    method: str,
    path: str,
    headers: dict[str, str],
    body: Any,
) -> dict:
    parsed = urlsplit(path)
    body_bytes = b"" if body is None else json.dumps(body).encode("utf-8")
    header_items = [
        (name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in headers.items()
    ]
    if body is not None and not any(name == b"content-type" for name, _ in header_items):
        header_items.append((b"content-type", b"application/json"))
    if body_bytes:
        header_items.append((b"content-length", str(len(body_bytes)).encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": parsed.path,
        "raw_path": parsed.path.encode("utf-8"),
        "query_string": parsed.query.encode("utf-8"),
        "headers": header_items,
        "client": ("transport-rpc", 0),
        "server": ("transport-rpc", 80),
        "root_path": "",
    }
    request_sent = False
    status = 500
    response_headers: list[tuple[bytes, bytes]] = []
    response_chunks: list[bytes] = []

    async def receive() -> dict:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    async def send(message: dict) -> None:
        nonlocal status, response_headers
        if message["type"] == "http.response.start":
            status = message["status"]
            response_headers = message.get("headers", [])
            return
        if message["type"] == "http.response.body":
            response_chunks.append(message.get("body", b""))
            return

    await app(scope, receive, send)
    content = b"".join(response_chunks)
    content_type = _header_value(response_headers, b"content-type")
    return {
        "status": status,
        "content_type": content_type,
        "body": _decode_body(content, content_type),
    }


def _header_value(headers: list[tuple[bytes, bytes]], name: bytes) -> str:
    for header_name, value in headers:
        if header_name.lower() == name:
            return value.decode("latin-1")
    return ""


def _decode_body(content: bytes, content_type: str) -> Any:
    if not content:
        return None
    if "application/json" in content_type:
        return json.loads(content.decode("utf-8"))
    return content.decode("utf-8")
