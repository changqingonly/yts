from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import _command_env, _configured_log_path, _frontend_env, _profile_settings
from .errors import ServctlError

RUN_DIR_NAME = "run"


@dataclass(frozen=True)
class ServerProcessConfig:
    root: Path
    profile: str
    host: str
    port: int
    reload: bool
    env: dict[str, str]
    pid_path: Path
    log_path: Path


@dataclass(frozen=True)
class FrontendProcessConfig:
    root: Path
    profile: str
    host: str
    port: int
    env: dict[str, str]
    frontend_dir: Path
    pid_path: Path
    log_path: Path


@dataclass(frozen=True)
class ComponentProcessConfig:
    root: Path
    profile: str
    name: str
    argv: list[str]
    env: dict[str, str]
    pid_path: Path
    log_path: Path


def spawn_server_process(config: ServerProcessConfig) -> int:
    config.pid_path.parent.mkdir(parents=True, exist_ok=True)
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "uv",
        "run",
        "uvicorn",
        "yts_server.main:app",
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]
    if config.reload:
        command.append("--reload")
    log_file = config.log_path.open("ab")
    process = subprocess.Popen(
        command,
        cwd=config.root,
        env=config.env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process.pid


def spawn_frontend_process(config: FrontendProcessConfig) -> int:
    config.pid_path.parent.mkdir(parents=True, exist_ok=True)
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "npm",
        "run",
        "preview",
        "--",
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--strictPort",
    ]
    log_file = config.log_path.open("ab")
    process = subprocess.Popen(
        command,
        cwd=config.frontend_dir,
        env=config.env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process.pid


def spawn_component_process(config: ComponentProcessConfig) -> int:
    config.pid_path.parent.mkdir(parents=True, exist_ok=True)
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = config.log_path.open("ab")
    process = subprocess.Popen(
        config.argv,
        cwd=config.root,
        env=config.env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process.pid


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        waited_pid, _ = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass
    else:
        if waited_pid == pid:
            return False
        if waited_pid == 0:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process(pid: int) -> None:
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        return


def _prepare_log_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab"):
        return


def _server_process_config(
    root: Path,
    profile: str,
    *,
    host: str,
    port: int,
    reload: bool,
) -> ServerProcessConfig:
    return ServerProcessConfig(
        root=root,
        profile=profile,
        host=host,
        port=port,
        reload=reload,
        env=_command_env(root, profile),
        pid_path=_pid_path(root, profile),
        log_path=_log_path(root, profile),
    )


def _frontend_process_config(
    root: Path,
    profile: str,
    *,
    host: str,
    port: int,
) -> FrontendProcessConfig:
    return FrontendProcessConfig(
        root=root,
        profile=profile,
        host=host,
        port=port,
        env=_frontend_env(root, profile),
        frontend_dir=root / "desktop" / "frontend",
        pid_path=_frontend_pid_path(root, profile),
        log_path=_frontend_log_path(root, profile),
    )


def _pid_path(root: Path, profile: str) -> Path:
    return root / RUN_DIR_NAME / f"yts-server-{profile}.pid"


def _log_path(root: Path, profile: str) -> Path:
    settings = _profile_settings(root, profile)
    return _configured_log_path(
        root,
        profile,
        log_dir=settings.logging.dir,
        file_template=settings.logging.backend_file,
    )


def _frontend_pid_path(root: Path, profile: str) -> Path:
    return root / RUN_DIR_NAME / f"yts-frontend-{profile}.pid"


def _frontend_log_path(root: Path, profile: str) -> Path:
    settings = _profile_settings(root, profile)
    return _configured_log_path(
        root,
        profile,
        log_dir=settings.logging.dir,
        file_template=settings.logging.frontend_file,
    )


def _stop_pid_file_process(
    pid_path: Path,
    process_name: str,
    profile: str,
    *,
    timeout_seconds: float,
    is_process_running_func: Callable[[int], bool] | None,
) -> None:
    is_process_running_func = is_process_running_func or _process_exists
    pid = _read_pid(pid_path)
    if pid is None:
        raise ServctlError(
            f"{process_name} is not running for profile {profile}; missing pid file {pid_path}"
        )
    if not is_process_running_func(pid):
        pid_path.unlink()
        return

    _terminate_process(pid)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_process_running_func(pid):
            pid_path.unlink()
            return
        time.sleep(0.2)
    raise ServctlError(f"{process_name} did not stop within {timeout_seconds:.1f}s: pid {pid}")


def _status_pid_file_process(
    pid_path: Path,
    process_name: str,
    profile: str,
    *,
    host: str,
    port: int,
    is_process_running_func: Callable[[int], bool] | None,
    is_port_in_use_func: Callable[[str, int, str], bool] | None,
) -> str:
    from .net import _is_port_in_use

    is_process_running_func = is_process_running_func or _process_exists
    is_port_in_use_func = is_port_in_use_func or _is_port_in_use
    pid = _read_pid(pid_path)
    if pid is None:
        if is_port_in_use_func(host, port, process_name):
            return (
                f"unmanaged port in use: profile={profile} port={host}:{port} pid_file={pid_path}"
            )
        return f"stopped: profile={profile} pid_file={pid_path}"
    if is_process_running_func(pid):
        return f"running: profile={profile} pid={pid}"
    if is_port_in_use_func(host, port, process_name):
        return (
            f"stale pid and unmanaged port in use: profile={profile} pid={pid} "
            f"port={host}:{port} pid_file={pid_path}"
        )
    return f"stale pid: profile={profile} pid={pid} pid_file={pid_path}"


def _read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ServctlError(f"pid file is empty: {path}")
    try:
        return int(raw)
    except ValueError as exc:
        raise ServctlError(f"pid file contains invalid pid: {path}: {raw}") from exc


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")
