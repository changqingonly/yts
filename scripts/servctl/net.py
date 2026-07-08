from __future__ import annotations

import errno
import socket
import time

from .errors import ServctlError


def _http_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _ensure_port_available(host: str, port: int, process_name: str) -> None:
    if _is_port_in_use(host, port, process_name):
        raise ServctlError(f"{process_name} port is already in use: {host}:{port}")


def _is_port_in_use(host: str, port: int, process_name: str) -> bool:
    result = _probe_port(host, port)
    if result == 0:
        return True
    if result != errno.ECONNREFUSED:
        raise ServctlError(f"{process_name} port probe failed for {host}:{port}: errno {result}")
    return False


def _probe_port(host: str, port: int) -> int:
    probe_host = _probe_host(host)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((probe_host, port))


def _probe_host(host: str) -> str:
    if host == "0.0.0.0":
        return "127.0.0.1"
    return host


def _wait_for_port_release(
    host: str,
    port: int,
    timeout_seconds: float,
    process_name: str,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            _ensure_port_available(host, port, process_name)
        except ServctlError:
            time.sleep(0.1)
            continue
        return
    raise ServctlError(
        f"{process_name} port did not release within {timeout_seconds:.1f}s: {host}:{port}"
    )
