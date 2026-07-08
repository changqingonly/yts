from __future__ import annotations

import os
from pathlib import Path
from string import Formatter

from .errors import ServctlError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PROFILE_DEFAULT_PORTS = {"cloud": 8000, "local": 8765}
DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 1420
DEFAULT_HEALTH_TIMEOUT_SECONDS = 30.0
REMOVED_CONFIG_ENV_NAMES = ("YTS_CONFIG_FILE", "YTS_CONFIG_HOME")
SUPPORTED_INFERENCE_BACKENDS = ("local", "cloud")
SKIP_STARTUP_DB_BOOTSTRAP_ENV = "YTS_SKIP_STARTUP_DB_BOOTSTRAP"


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
    if backend == "cloud" and _is_openai_compatible_model(default_text_model):
        if not env.get("YTS_OPENAI_API_KEY", "").strip():
            raise ServctlError(
                "YTS_OPENAI_API_KEY must be configured when "
                "YTS_INFERENCE_BACKEND=cloud and YTS_DEFAULT_TEXT_MODEL uses OpenAI-compatible"
            )


def _is_deepseek_model(model: str) -> bool:
    return model.startswith("deepseek/") or model.startswith("deepseek-")


def _is_openai_compatible_model(model: str) -> bool:
    return model.startswith("openai/") or model.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4"))


def _resolve_backend_port(profile: str, requested_port: int | None) -> int:
    if requested_port is not None:
        return requested_port
    try:
        return PROFILE_DEFAULT_PORTS[profile]
    except KeyError as exc:
        raise ServctlError(f"unsupported profile for backend port: {profile}") from exc


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


def _profile_settings(root: Path, profile: str):
    from yts_core.config import settings_from_env_mapping

    env = load_profile_env(root, profile)
    env["YTS_PROFILE"] = profile
    try:
        return settings_from_env_mapping(env)
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
