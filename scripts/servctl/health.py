from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import _command_env, require_profile_config
from .errors import ServctlError
from .net import _ensure_port_available


def run_preflight_checks(root: Path, profile: str, port: int, host: str) -> None:
    require_profile_config(root, profile)
    _ensure_port_available(host, port, "backend")
    env = _command_env(root, profile)
    _run_python_probe(root, env)


def wait_for_health(host: str, port: int, timeout_seconds: float) -> None:
    url = f"http://{host}:{port}/health"
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
                last_error = ServctlError(f"health returned HTTP {response.status}")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.25)
    if last_error is None:
        raise ServctlError(f"server health check timed out: {url}")
    raise ServctlError(f"server health check failed: {url}: {last_error}")


def wait_for_frontend(host: str, port: int, timeout_seconds: float) -> None:
    url = f"http://{host}:{port}/"
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
                last_error = ServctlError(f"frontend returned HTTP {response.status}")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.25)
    if last_error is None:
        raise ServctlError(f"frontend readiness check timed out: {url}")
    raise ServctlError(f"frontend readiness check failed: {url}: {last_error}")


def _run_python_probe(root: Path, env: dict[str, str]) -> None:
    completed = subprocess.run(
        ["uv", "run", "python", str(_preflight_probe_path())],
        cwd=root,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode == 0:
        return
    output = _tail_lines(
        "\n".join(part.strip() for part in [completed.stdout, completed.stderr] if part.strip()),
        40,
    )
    if not output:
        output = "<no output>"
    raise ServctlError(f"preflight probe failed with exit code {completed.returncode}:\n{output}")


def _tail_lines(value: str, line_count: int) -> str:
    lines = value.splitlines()
    return "\n".join(lines[-line_count:])


def _preflight_python_code(*, port: int, host: str) -> str:
    del port, host
    return _preflight_probe_path().read_text(encoding="utf-8")


def _preflight_probe_path() -> Path:
    return Path(__file__).with_name("preflight_probe.py")
