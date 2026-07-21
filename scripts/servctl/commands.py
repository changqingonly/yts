from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from .config import (
    DEFAULT_FRONTEND_HOST,
    DEFAULT_FRONTEND_PORT,
    DEFAULT_HEALTH_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    SKIP_STARTUP_DB_BOOTSTRAP_ENV,
    _command_env,
    _frontend_env,
    _require_file,
    _require_local_venv,
    require_profile_config,
)
from .errors import ServctlError
from .health import run_preflight_checks, wait_for_frontend, wait_for_health
from .net import _ensure_port_available, _http_url, _wait_for_port_release
from .process import (
    FrontendProcessConfig,
    ServerProcessConfig,
    _frontend_pid_path,
    _frontend_process_config,
    _local_gateway_pid_path,
    _pid_path,
    _prepare_log_file,
    _process_exists,
    _read_pid,
    _server_process_config,
    _spawn_local_gateway,
    _status_pid_file_process,
    _stop_pid_file_process,
    _terminate_process,
    _write_pid,
    spawn_frontend_process,
    spawn_server_process,
)

RunCommand = Callable[..., None]
ProgressReporter = Callable[[str], None]


def deploy(root: Path, profile: str, *, run_command: RunCommand = subprocess.check_call) -> None:
    require_profile_config(root, profile)
    _require_file(root / "uv.lock", "missing uv.lock; run dependency locking before deploy")
    _require_local_venv(root)
    frontend_dir = root / "desktop" / "frontend"
    _require_file(
        frontend_dir / "package-lock.json",
        "missing desktop/frontend/package-lock.json; npm ci requires a lock file",
    )

    env = _command_env(root, profile)
    run_command(
        ["uv", "run", "python", "-c", "from yts_core.config import get_settings; get_settings()"],
        cwd=root,
        env=env,
    )
    run_command(["npm", "run", "build"], cwd=frontend_dir, env=_frontend_env(root, profile))

    index_path = frontend_dir / "dist" / "index.html"
    if not index_path.is_file():
        raise ServctlError(f"frontend build did not produce {index_path}")


def install(root: Path, *, run_command: RunCommand = subprocess.check_call) -> None:
    run_command([str(root / "scripts" / "install.sh")], cwd=root)


def start(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    reload: bool = False,
    frontend_host: str = DEFAULT_FRONTEND_HOST,
    frontend_port: int = DEFAULT_FRONTEND_PORT,
    start_backend_func: Callable[..., None] | None = None,
    start_frontend_func: Callable[..., None] | None = None,
    check_frontend_func: Callable[..., FrontendProcessConfig] | None = None,
    stop_backend_func: Callable[..., None] | None = None,
    progress: ProgressReporter | None = None,
) -> None:
    start_backend_func = start_backend_func or start_server
    using_default_start_frontend = start_frontend_func is None
    start_frontend_func = start_frontend_func or start_frontend
    check_frontend_func = check_frontend_func or check_frontend_start_preconditions
    stop_backend_func = stop_backend_func or stop_server
    backend_kwargs = {"host": host, "port": port, "reload": reload}
    frontend_kwargs = {"host": frontend_host, "port": frontend_port}
    frontend_check_kwargs = {"host": frontend_host, "port": frontend_port}
    if progress is not None:
        backend_kwargs["progress"] = progress
        frontend_kwargs["progress"] = progress
        frontend_check_kwargs["progress"] = progress
    local_started = False
    backend_started = False
    try:
        if profile == "local":
            _report_progress(progress, "starting local inference gateway")
            _spawn_local_gateway(root, profile)
            local_started = True
            wait_for_health("127.0.0.1", 8799, DEFAULT_HEALTH_TIMEOUT_SECONDS)
        check_frontend_func(root, profile, **frontend_check_kwargs)
        if using_default_start_frontend:
            frontend_kwargs["check_preconditions"] = False
        start_backend_func(root, profile, **backend_kwargs)
        backend_started = True
        start_frontend_func(root, profile, **frontend_kwargs)
    except Exception:
        if local_started:
            _stop_pid_file_process(_local_gateway_pid_path(root), "gateway", profile,
                                   timeout_seconds=10.0, is_process_running_func=None)
        _report_progress(progress, "startup failed; stopping backend")
        if backend_started:
            stop_backend_func(root, profile, host=host, port=port)
        raise


def start_server(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    reload: bool = False,
    preflight: Callable[[Path, str, int, str], None] | None = None,
    spawn: Callable[[ServerProcessConfig], int] | None = None,
    wait_health: Callable[[str, int, float], None] | None = None,
    is_process_running: Callable[[int], bool] | None = None,
    terminate_process: Callable[[int], None] | None = None,
    progress: ProgressReporter | None = None,
) -> None:
    preflight = preflight or run_preflight_checks
    spawn = spawn or spawn_server_process
    wait_health = wait_health or wait_for_health
    is_process_running = is_process_running or _process_exists
    terminate_process = terminate_process or _terminate_process
    config = _server_process_config(root, profile, host=host, port=port, reload=reload)
    existing_pid = _read_pid(config.pid_path)
    if existing_pid is not None and is_process_running(existing_pid):
        raise ServctlError(f"server already running for profile {profile}: pid {existing_pid}")

    backend_url = _http_url(host, port)
    _report_progress(progress, f"preparing backend log: {config.log_path.name}")
    _prepare_log_file(config.log_path)
    _report_progress(progress, f"checking backend dependencies: {backend_url}")
    preflight(root, profile, port, host)
    config.env[SKIP_STARTUP_DB_BOOTSTRAP_ENV] = "1"
    _report_progress(progress, f"starting backend listener: {backend_url}")
    pid = spawn(config)
    _write_pid(config.pid_path, pid)
    try:
        wait_health(host, port, DEFAULT_HEALTH_TIMEOUT_SECONDS)
    except Exception:
        terminate_process(pid)
        if config.pid_path.exists():
            config.pid_path.unlink()
        raise
    _report_progress(progress, f"backend ready: {backend_url}")


def stop_server(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout_seconds: float = 10.0,
    is_process_running_func: Callable[[int], bool] | None = None,
    wait_port_release_func: Callable[[str, int, float, str], None] | None = None,
) -> None:
    wait_port_release_func = wait_port_release_func or _wait_for_port_release
    _stop_pid_file_process(
        _pid_path(root, profile),
        "server",
        profile,
        timeout_seconds=timeout_seconds,
        is_process_running_func=is_process_running_func,
    )
    wait_port_release_func(host, port, timeout_seconds, "backend")


def start_frontend(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_FRONTEND_HOST,
    port: int = DEFAULT_FRONTEND_PORT,
    spawn: Callable[[FrontendProcessConfig], int] | None = None,
    wait_ready: Callable[[str, int, float], None] | None = None,
    is_process_running: Callable[[int], bool] | None = None,
    terminate_process: Callable[[int], None] | None = None,
    check_preconditions: bool = True,
    progress: ProgressReporter | None = None,
) -> None:
    spawn = spawn or spawn_frontend_process
    wait_ready = wait_ready or wait_for_frontend
    is_process_running = is_process_running or _process_exists
    terminate_process = terminate_process or _terminate_process
    config = _frontend_process_config(root, profile, host=host, port=port)
    _report_progress(progress, f"preparing frontend log: {config.log_path.name}")
    _prepare_log_file(config.log_path)
    if check_preconditions:
        check_frontend_start_preconditions(
            root,
            profile,
            host=host,
            port=port,
            is_process_running=is_process_running,
            progress=progress,
        )
    frontend_url = _http_url(host, port)
    _report_progress(progress, f"starting frontend listener: {frontend_url}")
    pid = spawn(config)
    _write_pid(config.pid_path, pid)
    try:
        wait_ready(host, port, DEFAULT_HEALTH_TIMEOUT_SECONDS)
    except Exception:
        terminate_process(pid)
        if config.pid_path.exists():
            config.pid_path.unlink()
        raise
    _report_progress(progress, f"frontend ready: {frontend_url}")


def check_frontend_start_preconditions(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_FRONTEND_HOST,
    port: int = DEFAULT_FRONTEND_PORT,
    is_process_running: Callable[[int], bool] | None = None,
    progress: ProgressReporter | None = None,
) -> FrontendProcessConfig:
    is_process_running = is_process_running or _process_exists
    config = _frontend_process_config(root, profile, host=host, port=port)
    index_path = config.frontend_dir / "dist" / "index.html"
    _report_progress(progress, f"checking frontend build: {index_path}")
    _require_file(
        index_path,
        f"missing frontend build: {index_path}; run ./servctl deploy --profile {profile}",
    )
    existing_pid = _read_pid(config.pid_path)
    if existing_pid is not None and is_process_running(existing_pid):
        raise ServctlError(f"frontend already running for profile {profile}: pid {existing_pid}")
    _ensure_port_available(host, port, "frontend")
    return config


def stop_frontend(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_FRONTEND_HOST,
    port: int = DEFAULT_FRONTEND_PORT,
    timeout_seconds: float = 10.0,
    is_process_running_func: Callable[[int], bool] | None = None,
    wait_port_release_func: Callable[[str, int, float, str], None] | None = None,
) -> None:
    wait_port_release_func = wait_port_release_func or _wait_for_port_release
    _stop_pid_file_process(
        _frontend_pid_path(root, profile),
        "frontend",
        profile,
        timeout_seconds=timeout_seconds,
        is_process_running_func=is_process_running_func,
    )
    wait_port_release_func(host, port, timeout_seconds, "frontend")


def stop(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    frontend_host: str = DEFAULT_FRONTEND_HOST,
    frontend_port: int = DEFAULT_FRONTEND_PORT,
    stop_backend_func: Callable[..., None] = stop_server,
    stop_frontend_func: Callable[..., None] = stop_frontend,
    progress: ProgressReporter | None = None,
) -> None:
    errors: list[str] = []
    frontend_pid_path = _frontend_pid_path(root, profile)
    if frontend_pid_path.exists():
        try:
            _report_progress(progress, "stopping frontend")
            stop_frontend_func(root, profile, host=frontend_host, port=frontend_port)
            _report_progress(progress, "frontend stopped")
        except ServctlError as exc:
            errors.append(f"frontend: {exc}")
    try:
        _report_progress(progress, "stopping backend")
        stop_backend_func(root, profile, host=host, port=port)
        _report_progress(progress, "backend stopped")
    except ServctlError as exc:
        errors.append(f"backend: {exc}")
    if errors:
        raise ServctlError("; ".join(errors))
    if profile == "local":
        _stop_pid_file_process(_local_gateway_pid_path(root), "gateway", profile,
                               timeout_seconds=10.0, is_process_running_func=None)
        _wait_for_port_release("127.0.0.1", 8799, 10.0, "gateway")


def restart(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    reload: bool = False,
    frontend_host: str = DEFAULT_FRONTEND_HOST,
    frontend_port: int = DEFAULT_FRONTEND_PORT,
    deploy_func: Callable[[Path, str], None] = deploy,
    stop_func: Callable[..., None] = stop,
    start_func: Callable[..., None] = start,
) -> None:
    deploy_func(root, profile)
    stop_func(
        root,
        profile,
        host=host,
        port=port,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
    )
    start_func(
        root,
        profile,
        host=host,
        port=port,
        reload=reload,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
    )


def status_server(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    is_process_running_func: Callable[[int], bool] | None = None,
    is_port_in_use_func: Callable[[str, int, str], bool] | None = None,
) -> str:
    return _status_pid_file_process(
        _pid_path(root, profile),
        "backend",
        profile,
        host=host,
        port=port,
        is_process_running_func=is_process_running_func,
        is_port_in_use_func=is_port_in_use_func,
    )


def status_frontend(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_FRONTEND_HOST,
    port: int = DEFAULT_FRONTEND_PORT,
    is_process_running_func: Callable[[int], bool] | None = None,
    is_port_in_use_func: Callable[[str, int, str], bool] | None = None,
) -> str:
    return _status_pid_file_process(
        _frontend_pid_path(root, profile),
        "frontend",
        profile,
        host=host,
        port=port,
        is_process_running_func=is_process_running_func,
        is_port_in_use_func=is_port_in_use_func,
    )


def status(
    root: Path,
    profile: str,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    frontend_host: str = DEFAULT_FRONTEND_HOST,
    frontend_port: int = DEFAULT_FRONTEND_PORT,
    is_process_running_func: Callable[[int], bool] | None = None,
    is_port_in_use_func: Callable[[str, int, str], bool] | None = None,
) -> str:
    backend = status_server(
        root,
        profile,
        host=host,
        port=port,
        is_process_running_func=is_process_running_func,
        is_port_in_use_func=is_port_in_use_func,
    )
    frontend = status_frontend(
        root,
        profile,
        host=frontend_host,
        port=frontend_port,
        is_process_running_func=is_process_running_func,
        is_port_in_use_func=is_port_in_use_func,
    )
    if profile == "local":
        gateway = _status_pid_file_process(
            _local_gateway_pid_path(root), "gateway", profile,
            host="127.0.0.1", port=8799,
            is_process_running_func=is_process_running_func,
            is_port_in_use_func=is_port_in_use_func,
        )
        return f"backend: {backend}\nfrontend: {frontend}\ngateway: {gateway}"
    return f"backend: {backend}\nfrontend: {frontend}"


def _console_progress(message: str) -> None:
    print(f"servctl: {message}", flush=True)


def _report_progress(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)
