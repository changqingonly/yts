from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 1420
DEFAULT_HEALTH_TIMEOUT_SECONDS = 30.0
RUN_DIR_NAME = "run"
REMOVED_CONFIG_ENV_NAMES = ("YTS_CONFIG_FILE", "YTS_CONFIG_HOME")
SUPPORTED_INFERENCE_BACKENDS = ("echo", "cloud", "openai", "candle", "pro-fixture")


class ServctlError(RuntimeError):
    """Raised when a service control step fails explicitly."""


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


RunCommand = Callable[..., None]


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    try:
        if args.command == "deploy":
            deploy(root, args.profile)
        elif args.command == "install":
            install(root)
        elif args.command == "start":
            start(
                root,
                args.profile,
                host=args.host,
                port=args.port,
                reload=args.reload,
                frontend_host=args.frontend_host,
                frontend_port=args.frontend_port,
            )
        elif args.command == "stop":
            stop(root, args.profile)
        elif args.command == "restart":
            restart(
                root,
                args.profile,
                host=args.host,
                port=args.port,
                reload=args.reload,
                frontend_host=args.frontend_host,
                frontend_port=args.frontend_port,
            )
        elif args.command == "status":
            print(status(root, args.profile))
        else:
            parser.error(f"unsupported command: {args.command}")
    except ServctlError as exc:
        print(f"servctl: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        command = " ".join(exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
        print(
            f"servctl: command failed with exit code {exc.returncode}: {command}", file=sys.stderr
        )
        return exc.returncode or 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="servctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "install", help="bootstrap local uv, Python venv, Node, and frontend deps"
    )

    deploy_parser = subparsers.add_parser("deploy", help="check config and build frontend assets")
    deploy_parser.add_argument("--profile", default="cloud", choices=["cloud", "local"])

    start_parser = subparsers.add_parser("start", help="start the FastAPI server and web frontend")
    _add_server_args(start_parser)
    _add_frontend_args(start_parser)
    start_parser.add_argument(
        "--reload", action="store_true", help="start uvicorn with reload enabled"
    )

    stop_parser = subparsers.add_parser("stop", help="stop the FastAPI server and web frontend")
    stop_parser.add_argument("--profile", default="cloud", choices=["cloud", "local"])

    restart_parser = subparsers.add_parser(
        "restart", help="deploy, stop, then start the FastAPI server and web frontend"
    )
    _add_server_args(restart_parser)
    _add_frontend_args(restart_parser)
    restart_parser.add_argument(
        "--reload", action="store_true", help="start uvicorn with reload enabled"
    )

    status_parser = subparsers.add_parser("status", help="show FastAPI and web frontend status")
    status_parser.add_argument("--profile", default="cloud", choices=["cloud", "local"])
    return parser


def _add_server_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", default="cloud", choices=["cloud", "local"])
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)


def _add_frontend_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--frontend-host", default=DEFAULT_FRONTEND_HOST)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)


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
    stop_backend_func: Callable[[Path, str], None] | None = None,
) -> None:
    start_backend_func = start_backend_func or start_server
    start_frontend_func = start_frontend_func or start_frontend
    stop_backend_func = stop_backend_func or stop_server
    start_backend_func(root, profile, host=host, port=port, reload=reload)
    try:
        start_frontend_func(root, profile, host=frontend_host, port=frontend_port)
    except Exception:
        stop_backend_func(root, profile)
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

    preflight(root, profile, port, host)
    pid = spawn(config)
    _write_pid(config.pid_path, pid)
    try:
        wait_health(host, port, DEFAULT_HEALTH_TIMEOUT_SECONDS)
    except Exception:
        terminate_process(pid)
        if config.pid_path.exists():
            config.pid_path.unlink()
        raise


def stop_server(
    root: Path,
    profile: str,
    *,
    timeout_seconds: float = 10.0,
    is_process_running_func: Callable[[int], bool] | None = None,
) -> None:
    _stop_pid_file_process(
        _pid_path(root, profile),
        "server",
        profile,
        timeout_seconds=timeout_seconds,
        is_process_running_func=is_process_running_func,
    )


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
) -> None:
    spawn = spawn or spawn_frontend_process
    wait_ready = wait_ready or wait_for_frontend
    is_process_running = is_process_running or _process_exists
    terminate_process = terminate_process or _terminate_process
    config = _frontend_process_config(root, profile, host=host, port=port)
    index_path = config.frontend_dir / "dist" / "index.html"
    _require_file(
        index_path,
        f"missing frontend build: {index_path}; run ./servctl deploy --profile {profile}",
    )
    existing_pid = _read_pid(config.pid_path)
    if existing_pid is not None and is_process_running(existing_pid):
        raise ServctlError(f"frontend already running for profile {profile}: pid {existing_pid}")

    pid = spawn(config)
    _write_pid(config.pid_path, pid)
    try:
        wait_ready(host, port, DEFAULT_HEALTH_TIMEOUT_SECONDS)
    except Exception:
        terminate_process(pid)
        if config.pid_path.exists():
            config.pid_path.unlink()
        raise


def stop_frontend(
    root: Path,
    profile: str,
    *,
    timeout_seconds: float = 10.0,
    is_process_running_func: Callable[[int], bool] | None = None,
) -> None:
    _stop_pid_file_process(
        _frontend_pid_path(root, profile),
        "frontend",
        profile,
        timeout_seconds=timeout_seconds,
        is_process_running_func=is_process_running_func,
    )


def stop(
    root: Path,
    profile: str,
    *,
    stop_backend_func: Callable[[Path, str], None] = stop_server,
    stop_frontend_func: Callable[[Path, str], None] = stop_frontend,
) -> None:
    errors: list[str] = []
    frontend_pid_path = _frontend_pid_path(root, profile)
    if frontend_pid_path.exists():
        try:
            stop_frontend_func(root, profile)
        except ServctlError as exc:
            errors.append(f"frontend: {exc}")
    try:
        stop_backend_func(root, profile)
    except ServctlError as exc:
        errors.append(f"backend: {exc}")
    if errors:
        raise ServctlError("; ".join(errors))


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
    stop_func: Callable[[Path, str], None] = stop,
    start_func: Callable[..., None] = start,
) -> None:
    deploy_func(root, profile)
    stop_func(root, profile)
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
    is_process_running_func: Callable[[int], bool] | None = None,
) -> str:
    return _status_pid_file_process(
        _pid_path(root, profile),
        profile,
        is_process_running_func=is_process_running_func,
    )


def status_frontend(
    root: Path,
    profile: str,
    *,
    is_process_running_func: Callable[[int], bool] | None = None,
) -> str:
    return _status_pid_file_process(
        _frontend_pid_path(root, profile),
        profile,
        is_process_running_func=is_process_running_func,
    )


def status(
    root: Path,
    profile: str,
    *,
    is_process_running_func: Callable[[int], bool] | None = None,
) -> str:
    backend = status_server(
        root, profile, is_process_running_func=is_process_running_func
    )
    frontend = status_frontend(
        root, profile, is_process_running_func=is_process_running_func
    )
    return f"backend: {backend}\nfrontend: {frontend}"


def run_preflight_checks(root: Path, profile: str, port: int, host: str) -> None:
    require_profile_config(root, profile)
    env = _command_env(root, profile)
    _run_python_probe(root, env, _preflight_python_code(port=port, host=host))


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
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process.pid


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


def require_profile_config(root: Path, profile: str) -> Path:
    config_path = root / "conf" / f"{profile}.env"
    if not config_path.is_file():
        raise ServctlError(
            f"missing required config file: {config_path}; copy conf/{profile}.example.env and fill real values"
        )
    return config_path


def load_profile_env(root: Path, profile: str) -> dict[str, str]:
    config_path = require_profile_config(root, profile)
    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        config_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise ServctlError(f"invalid env line in {config_path}:{line_number}: missing '='")
        name, value = line.split("=", 1)
        name = name.strip()
        if not name:
            raise ServctlError(
                f"invalid env line in {config_path}:{line_number}: empty variable name"
            )
        parsed[name] = _unquote_env_value(value.strip())
    return parsed


def validate_profile_config(root: Path, profile: str) -> None:
    env = load_profile_env(root, profile)
    backend = env.get("YTS_INFERENCE_BACKEND", "").strip()
    if backend and backend not in SUPPORTED_INFERENCE_BACKENDS:
        supported = ", ".join(SUPPORTED_INFERENCE_BACKENDS)
        raise ServctlError(
            f"unsupported YTS_INFERENCE_BACKEND={backend}; supported values: {supported}. "
            "For DeepSeek via LiteLLM, use YTS_INFERENCE_BACKEND=cloud and "
            "YTS_DEFAULT_TEXT_MODEL=deepseek/deepseek-chat"
        )
    default_text_model = env.get("YTS_DEFAULT_TEXT_MODEL", "").strip()
    if backend == "cloud" and _is_deepseek_model(default_text_model):
        if not env.get("YTS_DEEPSEEK_API_KEY", "").strip():
            raise ServctlError(
                "YTS_DEEPSEEK_API_KEY must be configured when "
                "YTS_INFERENCE_BACKEND=cloud and YTS_DEFAULT_TEXT_MODEL uses DeepSeek"
            )


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_deepseek_model(model: str) -> bool:
    return model.startswith("deepseek/") or model.startswith("deepseek-")


def _terminate_process(pid: int) -> None:
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
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


def _command_env(root: Path, profile: str) -> dict[str, str]:
    _reject_removed_config_env()
    validate_profile_config(root, profile)
    env = dict(os.environ)
    env.update(load_profile_env(root, profile))
    env["YTS_PROFILE"] = profile
    env["YTS_CONFIG_DIR"] = str(root / "conf")
    env["PATH"] = _tool_path(root, env.get("PATH", ""))
    return env


def _frontend_env(root: Path, profile: str) -> dict[str, str]:
    env = _command_env(root, profile)
    env["VITE_YTS_DEFAULT_TARGET"] = profile
    return env


def _tool_path(root: Path, current_path: str) -> str:
    tool_dirs = [
        root / ".tools" / "uv",
        root / ".tools" / "node" / "bin",
    ]
    path_values = [str(path) for path in tool_dirs if path.is_dir()]
    if current_path:
        path_values.append(current_path)
    return os.pathsep.join(path_values)


def _reject_removed_config_env() -> None:
    configured = [name for name in REMOVED_CONFIG_ENV_NAMES if os.environ.get(name, "").strip()]
    if configured:
        names = ", ".join(configured)
        unset_commands = " ".join(f"unset {name};" for name in configured).rstrip(";")
        raise ServctlError(
            f"{names} is no longer supported; remove it from your shell environment "
            f"({unset_commands}) and use conf/{{profile}}.env or YTS_CONFIG_DIR"
        )


def _run_python_probe(root: Path, env: dict[str, str], code: str) -> None:
    subprocess.check_call(["uv", "run", "python", "-c", code], cwd=root, env=env)


def _preflight_python_code(*, port: int, host: str) -> str:
    return f"""
import asyncio
import socket

from sqlalchemy import text

from yts_core.config import get_settings
from yts_core.inference.factory import make_backend
from yts_server.db.session import get_engine
from yts_server.main import create_app


async def main():
    settings = get_settings()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(({host!r}, {port!r}))
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    backend = make_backend(settings)
    if settings.inference_backend == "pro-fixture":
        messages = [{{"role": "user", "content": "YTS_PRO_STAGE: parse_intent"}}]
    else:
        messages = [{{"role": "user", "content": "Return the word ok."}}]
    result = await backend.generate_text(messages)
    if not result.text.strip():
        raise RuntimeError("LLM preflight returned empty text")
    app = create_app()
    if app.state.settings.profile != settings.profile:
        raise RuntimeError("app settings profile mismatch")


asyncio.run(main())
"""


def _pid_path(root: Path, profile: str) -> Path:
    return root / RUN_DIR_NAME / f"yts-server-{profile}.pid"


def _log_path(root: Path, profile: str) -> Path:
    return root / RUN_DIR_NAME / f"yts-server-{profile}.log"


def _frontend_pid_path(root: Path, profile: str) -> Path:
    return root / RUN_DIR_NAME / f"yts-frontend-{profile}.pid"


def _frontend_log_path(root: Path, profile: str) -> Path:
    return root / RUN_DIR_NAME / f"yts-frontend-{profile}.log"


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
        raise ServctlError(f"pid file exists but process is not running: {pid}")

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
    profile: str,
    *,
    is_process_running_func: Callable[[int], bool] | None,
) -> str:
    is_process_running_func = is_process_running_func or _process_exists
    pid = _read_pid(pid_path)
    if pid is None:
        return f"stopped: profile={profile} pid_file={pid_path}"
    if is_process_running_func(pid):
        return f"running: profile={profile} pid={pid}"
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


def _require_file(path: Path, message: str) -> None:
    if not path.is_file():
        raise ServctlError(message)


def _require_local_venv(root: Path) -> None:
    venv = root / ".venv"
    if not venv.is_dir():
        raise ServctlError("missing local Python environment: run ./install before deploy")


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
