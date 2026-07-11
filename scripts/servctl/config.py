from __future__ import annotations

import os
from pathlib import Path
from string import Formatter

from yts_core.config import (
    SUPPORTED_INFERENCE_BACKENDS as _CORE_SUPPORTED_INFERENCE_BACKENDS,
)
from yts_core.config import _is_deepseek_model as _core_is_deepseek_model
from yts_core.config import (
    _is_openai_compatible_model as _core_is_openai_compatible_model,
)
from yts_core.config import load_profile_config as _load_canonical_profile_config

from .errors import ServctlError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PROFILE_DEFAULT_PORTS = {"cloud": 8000, "local": 8765}
DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 1420
DEFAULT_HEALTH_TIMEOUT_SECONDS = 30.0
REMOVED_CONFIG_ENV_NAMES = ("YTS_CONFIG_FILE", "YTS_CONFIG_HOME")
SUPPORTED_INFERENCE_BACKENDS = _CORE_SUPPORTED_INFERENCE_BACKENDS
SKIP_STARTUP_DB_BOOTSTRAP_ENV = "YTS_SKIP_STARTUP_DB_BOOTSTRAP"


def require_profile_config(root: Path, profile: str) -> Path:
    return _loaded_profile_config(root, profile).path


def load_profile_env(root: Path, profile: str) -> dict[str, str]:
    return dict(_loaded_profile_config(root, profile).values)


def validate_profile_config(root: Path, profile: str) -> None:
    _loaded_profile_config(root, profile)


def _is_deepseek_model(model: str) -> bool:
    return _core_is_deepseek_model(model)


def _is_openai_compatible_model(model: str) -> bool:
    return _core_is_openai_compatible_model(model)


def _resolve_backend_port(profile: str, requested_port: int | None) -> int:
    if requested_port is not None:
        return requested_port
    try:
        return PROFILE_DEFAULT_PORTS[profile]
    except KeyError as exc:
        raise ServctlError(f"unsupported profile for backend port: {profile}") from exc


def _command_env(root: Path, profile: str) -> dict[str, str]:
    loaded = _loaded_profile_config(root, profile)
    env = dict(os.environ)
    env.update(loaded.values)
    env["YTS_PROFILE"] = profile
    env["YTS_CONFIG_DIR"] = str(loaded.path.parent)
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


def _profile_settings(root: Path, profile: str):
    return _loaded_profile_config(root, profile).settings


def _loaded_profile_config(root: Path, profile: str):
    _reject_removed_config_env()
    configured_dir = os.environ.get("YTS_CONFIG_DIR", "").strip()
    config_dir = None if configured_dir else root / "conf"
    try:
        return _load_canonical_profile_config(
            profile,
            config_dir=config_dir,
            environ=os.environ,
        )
    except FileNotFoundError as exc:
        selected_dir = Path(configured_dir).expanduser() if configured_dir else root / "conf"
        config_path = selected_dir / f"{profile}.env"
        raise ServctlError(
            f"missing required config file: {config_path}; "
            f"copy conf/{profile}.example.env and fill real values: {exc}"
        ) from exc
    except Exception as exc:
        raise ServctlError(f"invalid profile config for {profile}: {exc}") from exc


def _configured_log_path(root: Path, profile: str, *, log_dir: str, file_template: str) -> Path:
    log_file = _format_log_file(file_template, profile)
    log_file_path = Path(log_file)
    if log_file_path.is_absolute():
        raise ServctlError(
            "logging file templates must be relative; configure absolute directories with "
            "YTS_LOGGING_DIR"
        )
    if ".." in log_file_path.parts:
        raise ServctlError("logging file templates must not contain '..'")

    log_dir_path = Path(log_dir).expanduser()
    if not log_dir_path.is_absolute():
        log_dir_path = root / log_dir_path
    return log_dir_path / log_file_path


def _format_log_file(file_template: str, profile: str) -> str:
    allowed_fields = {"profile"}
    try:
        parsed_template = list(Formatter().parse(file_template))
    except ValueError as exc:
        raise ServctlError(f"invalid log file template {file_template!r}: {exc}") from exc
    for _, field_name, _, _ in parsed_template:
        if field_name is None:
            continue
        if field_name not in allowed_fields:
            raise ServctlError(
                f"unsupported log file template variable {{{field_name}}}; "
                "only {profile} is supported"
            )
    try:
        return file_template.format(profile=profile)
    except ValueError as exc:
        raise ServctlError(f"invalid log file template {file_template!r}: {exc}") from exc


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
