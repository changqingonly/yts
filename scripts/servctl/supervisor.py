from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from yts_core.components import (
    ComponentManifest,
    ComponentSpec,
    RuntimeSpec,
    expand_argv,
    load_component_manifest,
    resolve_component_paths,
)

from .component_commands import ComponentResult, status_components, verify_components
from .config import _tool_path
from .errors import ServctlError
from .net import _wait_for_port_release
from .process import (
    ComponentProcessConfig,
    RUN_DIR_NAME,
    _process_exists,
    _read_pid,
    _stop_pid_file_process,
    _write_pid,
    spawn_component_process,
)
from .runtime_config import write_frontend_runtime_config

LOCK_SCHEMA_VERSION = 1
LOCK_OWNER_SERVCTL = "servctl"
LOCK_OWNER_TAURI = "tauri"
LOCAL_REQUIRED_COMPONENTS = ("llama", "stable-diffusion", "infer-gateway")
LOCAL_SERVICE_COMPONENTS = ("llama", "infer-gateway")
LOCAL_COMPONENT_STOP_ORDER = tuple(reversed(LOCAL_SERVICE_COMPONENTS))
_MANIFEST_PATH = Path("desktop/components.toml")

ProgressReporter = Callable[[str], None]


@dataclass(frozen=True)
class OwnershipLock:
    path: Path
    owner: str
    pid: int

    def release(self) -> None:
        release_ownership_lock(self.path.parent.parent, self.owner, pid=self.pid)


def local_supervisor_lock_path(root: Path) -> Path:
    return root / RUN_DIR_NAME / "yts-local-supervisor.lock"


def component_pid_path(root: Path, profile: str, name: str) -> Path:
    return root / RUN_DIR_NAME / f"yts-component-{profile}-{name}.pid"


def component_log_path(root: Path, profile: str, name: str) -> Path:
    return root / RUN_DIR_NAME / f"yts-component-{profile}-{name}.log"


def acquire_ownership_lock(
    root: Path,
    owner: str,
    *,
    pid: int | None = None,
    process_exists: Callable[[int], bool] = _process_exists,
) -> OwnershipLock:
    if owner not in {LOCK_OWNER_SERVCTL, LOCK_OWNER_TAURI}:
        raise ServctlError(f"unsupported local supervisor owner: {owner}")
    selected_pid = os.getpid() if pid is None else pid
    if selected_pid <= 0:
        raise ServctlError(f"local supervisor owner pid must be positive: {selected_pid}")
    path = local_supervisor_lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": LOCK_SCHEMA_VERSION,
        "owner": owner,
        "pid": selected_pid,
        "startedAt": _utc_now(),
    }

    while True:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            record = _read_lock_record(path)
            existing_pid = record["pid"]
            if process_exists(existing_pid):
                raise ServctlError(
                    f"local runtime is owned by {record['owner']}: pid {existing_pid}"
                )
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.write("\n")
        return OwnershipLock(path=path, owner=owner, pid=selected_pid)


def release_ownership_lock(root: Path, owner: str, *, pid: int | None = None) -> None:
    path = local_supervisor_lock_path(root)
    if not path.exists():
        return
    record = _read_lock_record(path)
    if record["owner"] != owner:
        raise ServctlError(
            f"local runtime lock is owned by {record['owner']}, not {owner}: {path}"
        )
    if pid is not None and record["pid"] != pid:
        raise ServctlError(
            f"local runtime lock pid mismatch for {owner}: expected {pid}, found {record['pid']}"
        )
    path.unlink()


def check_ownership_for_stop(
    root: Path,
    owner: str,
    *,
    process_exists: Callable[[int], bool] = _process_exists,
) -> None:
    path = local_supervisor_lock_path(root)
    if not path.exists():
        return
    record = _read_lock_record(path)
    if record["owner"] == owner:
        return
    if process_exists(record["pid"]):
        raise ServctlError(f"local runtime is owned by {record['owner']}: pid {record['pid']}")
    path.unlink()


def start_local_runtime(
    root: Path,
    profile: str,
    *,
    host: str,
    port: int,
    reload: bool,
    frontend_host: str,
    frontend_port: int,
    acquire_lock_func: Callable[..., OwnershipLock] | None = None,
    verify_components_func: Callable[..., list[ComponentResult]] | None = None,
    start_component_func: Callable[..., None] | None = None,
    wait_component_ready_func: Callable[..., None] | None = None,
    start_backend_func: Callable[..., None] | None = None,
    write_runtime_config_func: Callable[[Path, str], object] | None = None,
    start_frontend_func: Callable[..., None] | None = None,
    stop_backend_func: Callable[..., None] | None = None,
    stop_component_func: Callable[..., None] | None = None,
    progress: ProgressReporter | None = None,
) -> None:
    if profile != "local":
        raise ServctlError(f"local supervisor requires profile local, got {profile}")
    if start_backend_func is None or start_frontend_func is None or stop_backend_func is None:
        from .commands import start_frontend, start_server, stop_server

        start_backend_func = start_backend_func or start_server
        start_frontend_func = start_frontend_func or start_frontend
        stop_backend_func = stop_backend_func or stop_server

    acquire_lock_func = acquire_lock_func or acquire_ownership_lock
    verify_components_func = verify_components_func or verify_components
    using_default_start_component = start_component_func is None
    start_component_func = start_component_func or start_component
    wait_component_ready_func = wait_component_ready_func or wait_component_ready
    write_runtime_config_func = write_runtime_config_func or write_frontend_runtime_config
    stop_component_func = stop_component_func or stop_component

    lock = acquire_lock_func(root, LOCK_OWNER_SERVCTL)
    started_components: list[str] = []
    backend_started = False
    try:
        for name in LOCAL_REQUIRED_COMPONENTS:
            _require_ready_component(name, verify_components_func(root, [name]))

        for name in LOCAL_SERVICE_COMPONENTS:
            extra_env = (
                build_gateway_environment(root)
                if name == "infer-gateway" and using_default_start_component
                else None
            )
            start_component_func(root, profile, name, extra_env=extra_env, progress=progress)
            started_components.append(name)
            wait_component_ready_func(root, profile, name, progress=progress)

        start_backend_func(root, profile, host=host, port=port, reload=reload, progress=progress)
        backend_started = True
        write_runtime_config_func(root, profile)
        start_frontend_func(
            root,
            profile,
            host=frontend_host,
            port=frontend_port,
            write_runtime_config=False,
            progress=progress,
        )
    except Exception:
        errors = []
        if backend_started:
            try:
                stop_backend_func(root, profile, host=host, port=port)
            except ServctlError as exc:
                errors.append(f"backend rollback: {exc}")
        for name in reversed(started_components):
            try:
                stop_component_func(root, profile, name)
            except ServctlError as exc:
                errors.append(f"{name} rollback: {exc}")
        try:
            lock.release()
        except ServctlError as exc:
            errors.append(f"lock rollback: {exc}")
        if errors:
            raise ServctlError("; ".join(errors)) from None
        raise


def stop_local_runtime(
    root: Path,
    profile: str,
    *,
    host: str,
    port: int,
    frontend_host: str,
    frontend_port: int,
    check_lock_func: Callable[..., None] | None = None,
    stop_frontend_func: Callable[..., None] | None = None,
    stop_backend_func: Callable[..., None] | None = None,
    stop_component_func: Callable[..., None] | None = None,
    release_lock_func: Callable[..., None] | None = None,
    progress: ProgressReporter | None = None,
) -> None:
    if profile != "local":
        raise ServctlError(f"local supervisor requires profile local, got {profile}")
    if stop_frontend_func is None or stop_backend_func is None:
        from .commands import stop_frontend, stop_server

        stop_frontend_func = stop_frontend_func or stop_frontend
        stop_backend_func = stop_backend_func or stop_server

    check_lock_func = check_lock_func or check_ownership_for_stop
    stop_component_func = stop_component_func or stop_component
    release_lock_func = release_lock_func or release_ownership_lock

    check_lock_func(root, LOCK_OWNER_SERVCTL)
    errors: list[str] = []
    for label, action in [
        (
            "frontend",
            lambda: stop_frontend_func(
                root,
                profile,
                host=frontend_host,
                port=frontend_port,
            ),
        ),
        ("backend", lambda: stop_backend_func(root, profile, host=host, port=port)),
        (
            "infer-gateway",
            lambda: stop_component_func(root, profile, "infer-gateway"),
        ),
        ("llama", lambda: stop_component_func(root, profile, "llama")),
    ]:
        _report_progress(progress, f"stopping {label}")
        try:
            action()
        except ServctlError as exc:
            errors.append(f"{label}: {exc}")
    try:
        release_lock_func(root, LOCK_OWNER_SERVCTL)
    except ServctlError as exc:
        errors.append(f"lock: {exc}")
    if errors:
        raise ServctlError("; ".join(errors))


def start_component(
    root: Path,
    profile: str,
    name: str,
    *,
    extra_env: dict[str, str] | None = None,
    spawn: Callable[[ComponentProcessConfig], int] = spawn_component_process,
    is_process_running: Callable[[int], bool] = _process_exists,
    progress: ProgressReporter | None = None,
) -> None:
    manifest = _load_manifest(root)
    resolved = resolve_component_paths(root, manifest, name)
    runtime = _require_service_runtime(name, resolved.component)
    existing_pid = _read_pid(component_pid_path(root, profile, name))
    if existing_pid is not None and is_process_running(existing_pid):
        raise ServctlError(f"component {name} already running for profile {profile}: pid {existing_pid}")
    try:
        argv = expand_argv(runtime.argv, resolved.argv_tokens())
    except (TypeError, ValueError) as exc:
        raise ServctlError(f"invalid runtime argv for component {name}: {exc}") from exc
    config = ComponentProcessConfig(
        root=root,
        profile=profile,
        name=name,
        argv=argv,
        env=_component_env(root, extra_env),
        pid_path=component_pid_path(root, profile, name),
        log_path=component_log_path(root, profile, name),
    )
    _report_progress(progress, f"starting component {name}")
    pid = spawn(config)
    _write_pid(config.pid_path, pid)


def wait_component_ready(
    root: Path,
    profile: str,
    name: str,
    *,
    progress: ProgressReporter | None = None,
) -> None:
    del profile
    manifest = _load_manifest(root)
    runtime = _require_service_runtime(name, manifest.components[name])
    readiness = _require_value(runtime.readiness, f"{name} runtime requires readiness")
    host = _require_value(runtime.host, f"{name} runtime requires host")
    port = _require_value(runtime.port, f"{name} runtime requires port")
    _report_progress(progress, f"waiting for component {name}")
    _wait_for_http_path(host, port, readiness.path, readiness.timeout_seconds)


def stop_component(
    root: Path,
    profile: str,
    name: str,
    *,
    is_process_running_func: Callable[[int], bool] | None = None,
    wait_port_release_func: Callable[[str, int, float, str], None] | None = None,
) -> None:
    wait_port_release_func = wait_port_release_func or _wait_for_port_release
    manifest = _load_manifest(root)
    runtime = _require_service_runtime(name, manifest.components[name])
    timeout = _require_value(
        runtime.shutdown_timeout_seconds,
        f"{name} runtime requires shutdown_timeout_seconds",
    )
    _stop_pid_file_process(
        component_pid_path(root, profile, name),
        f"component {name}",
        profile,
        timeout_seconds=float(timeout),
        is_process_running_func=is_process_running_func,
    )
    host = _require_value(runtime.host, f"{name} runtime requires host")
    port = _require_value(runtime.port, f"{name} runtime requires port")
    wait_port_release_func(host, port, float(timeout), name)


def build_gateway_environment(
    root: Path,
    manifest: ComponentManifest | None = None,
) -> dict[str, str]:
    selected_manifest = manifest or _load_manifest(root)
    gateway = selected_manifest.components["infer-gateway"]
    llama = selected_manifest.components["llama"]
    image = selected_manifest.components["stable-diffusion"]
    audio = selected_manifest.components["acestep"]

    gateway_runtime = _require_service_runtime("infer-gateway", gateway)
    llama_runtime = _require_service_runtime("llama", llama)
    image_runtime = _require_command_runtime("stable-diffusion", image)

    llama_model = _require_single_llama_model(llama)
    _require_llama_alias(llama_runtime.argv, llama_model.id)

    resolved_image = resolve_component_paths(root, selected_manifest, "stable-diffusion")
    image_argv = _expand_component_argv("stable-diffusion", image_runtime, resolved_image.argv_tokens())
    image_limits = _require_value(image_runtime.limits, "stable-diffusion runtime requires limits")

    env = {
        "YTS_GATEWAY_ADDR": _host_port(
            _require_value(gateway_runtime.host, "infer-gateway runtime requires host"),
            _require_value(gateway_runtime.port, "infer-gateway runtime requires port"),
        ),
        "YTS_GATEWAY_SHUTDOWN_TIMEOUT_SECONDS": str(
            _require_value(
                gateway_runtime.shutdown_timeout_seconds,
                "infer-gateway runtime requires shutdown_timeout_seconds",
            )
        ),
        "YTS_LLAMA_BASE_URL": _http_base_url(
            _require_value(llama_runtime.host, "llama runtime requires host"),
            _require_value(llama_runtime.port, "llama runtime requires port"),
        ),
        "YTS_LLAMA_STARTUP_TIMEOUT_SECONDS": str(
            _require_value(
                llama_runtime.startup_timeout_seconds,
                "llama runtime requires startup_timeout_seconds",
            )
        ),
        "YTS_LLAMA_PROBE_TIMEOUT_SECONDS": str(
            _require_value(
                _require_value(llama_runtime.readiness, "llama runtime requires readiness").timeout_seconds,
                "llama readiness requires timeout_seconds",
            )
        ),
        "YTS_LLAMA_COMPLETION_TIMEOUT_SECONDS": str(
            _require_value(
                gateway_runtime.request_timeout_seconds,
                "infer-gateway runtime requires request_timeout_seconds",
            )
        ),
        "YTS_LLAMA_MODEL": llama_model.id,
        "YTS_IMAGEGEN_ENABLED": "true" if image.enabled else "false",
        "YTS_IMAGEGEN_ARGV": json.dumps(image_argv, separators=(",", ":")),
        "YTS_IMAGEGEN_TIMEOUT_SECONDS": str(
            _require_value(
                image_runtime.execution_timeout_seconds,
                "stable-diffusion runtime requires execution_timeout_seconds",
            )
        ),
        "YTS_IMAGEGEN_MAX_OUTPUT_BYTES": str(
            _require_value(
                image_limits.max_output_bytes,
                "stable-diffusion limits require max_output_bytes",
            )
        ),
        "YTS_IMAGEGEN_MAX_CONCURRENCY": str(
            _require_value(
                image_limits.max_concurrency,
                "stable-diffusion limits require max_concurrency",
            )
        ),
        "YTS_IMAGEGEN_MAX_WIDTH": str(
            _require_value(image_limits.max_width, "stable-diffusion limits require max_width")
        ),
        "YTS_IMAGEGEN_MAX_HEIGHT": str(
            _require_value(image_limits.max_height, "stable-diffusion limits require max_height")
        ),
        "YTS_IMAGEGEN_MAX_STEPS": str(
            _require_value(image_limits.max_steps, "stable-diffusion limits require max_steps")
        ),
    }
    if audio.enabled:
        raise ServctlError(
            "acestep audio generation is not supported until the manifest declares gateway limits"
        )
    env["YTS_AUDIOGEN_ENABLED"] = "false"
    return env


def local_status(root: Path, profile: str) -> str:
    results = status_components(root, profile)
    lines = ["components:"]
    lines.extend(f"{result.name}: {result.state} - {result.detail}" for result in results)
    return "\n".join(lines)


def _require_ready_component(name: str, results: Sequence[ComponentResult]) -> None:
    if len(results) != 1 or results[0].name != name:
        raise ServctlError(f"component verification for {name} returned unexpected results")
    result = results[0]
    if result.enabled and result.state == "ready":
        return
    raise ServctlError(
        f"component {name} is {result.state}: {result.detail}; "
        f"run ./servctl components install {name}"
    )


def _load_manifest(root: Path) -> ComponentManifest:
    try:
        return load_component_manifest(root / _MANIFEST_PATH)
    except (OSError, ValueError) as exc:
        raise ServctlError(f"invalid component manifest: {exc}") from exc


def _require_service_runtime(name: str, component: ComponentSpec) -> RuntimeSpec:
    if component.runtime.kind != "service":
        raise ServctlError(f"{name} runtime must be service")
    return component.runtime


def _require_command_runtime(name: str, component: ComponentSpec) -> RuntimeSpec:
    if component.runtime.kind != "command":
        raise ServctlError(f"{name} runtime must be command")
    return component.runtime


def _require_single_llama_model(component: ComponentSpec):
    if len(component.models) != 1:
        raise ServctlError("llama must declare exactly one model")
    return component.models[0]


def _require_llama_alias(argv: Sequence[str], model_id: str) -> None:
    alias_positions = [index for index, argument in enumerate(argv) if argument == "--alias"]
    if len(alias_positions) != 1:
        raise ServctlError("llama runtime argv must contain exactly one --alias")
    alias_index = alias_positions[0]
    if alias_index + 1 >= len(argv):
        raise ServctlError("llama runtime --alias must be followed by the model id")
    alias = argv[alias_index + 1]
    if alias != model_id:
        raise ServctlError(f"llama runtime --alias must match model id {model_id}")


def _expand_component_argv(name: str, runtime: RuntimeSpec, tokens) -> list[str]:
    try:
        return expand_argv(runtime.argv, tokens)
    except (TypeError, ValueError) as exc:
        raise ServctlError(f"invalid runtime argv for component {name}: {exc}") from exc


def _require_value(value, message: str):
    if value is None:
        raise ServctlError(message)
    return value


def _host_port(host: str, port: int) -> str:
    return f"{_format_host(host)}:{port}"


def _http_base_url(host: str, port: int) -> str:
    return f"http://{_format_host(host)}:{port}"


def _format_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _component_env(root: Path, extra_env: dict[str, str] | None) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if name in {"PATH", "HOME", "TMPDIR", "LANG", "TERM"} or name.startswith("LC_")
    }
    tool_path = _tool_path(root, env.get("PATH", ""))
    if tool_path:
        env["PATH"] = tool_path
    if extra_env:
        env.update(extra_env)
    return env


def _wait_for_http_path(host: str, port: int, path: str, timeout_seconds: int) -> None:
    url = f"http://{_format_host(host)}:{port}{path}"
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 300:
                    return
                last_error = ServctlError(f"HTTP {response.status}")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise ServctlError(f"component readiness check failed: {url}: {last_error}")


def _read_lock_record(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServctlError(f"invalid local runtime lock {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ServctlError(f"invalid local runtime lock {path}: expected object")
    schema_version = raw.get("schemaVersion")
    owner = raw.get("owner")
    pid = raw.get("pid")
    started_at = raw.get("startedAt")
    if schema_version != LOCK_SCHEMA_VERSION:
        raise ServctlError(f"unsupported local runtime lock schema: {schema_version}")
    if owner not in {LOCK_OWNER_SERVCTL, LOCK_OWNER_TAURI}:
        raise ServctlError(f"invalid local runtime lock owner: {owner}")
    if not isinstance(pid, int) or pid <= 0:
        raise ServctlError(f"invalid local runtime lock pid: {pid}")
    if not isinstance(started_at, str) or not started_at:
        raise ServctlError("invalid local runtime lock startedAt")
    return {"schemaVersion": schema_version, "owner": owner, "pid": pid, "startedAt": started_at}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _report_progress(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)


__all__ = [
    "LOCK_OWNER_SERVCTL",
    "LOCK_OWNER_TAURI",
    "OwnershipLock",
    "acquire_ownership_lock",
    "build_gateway_environment",
    "check_ownership_for_stop",
    "component_log_path",
    "component_pid_path",
    "local_status",
    "local_supervisor_lock_path",
    "release_ownership_lock",
    "start_component",
    "start_local_runtime",
    "stop_component",
    "stop_local_runtime",
    "wait_component_ready",
]
