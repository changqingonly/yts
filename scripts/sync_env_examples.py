from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

ASSIGNMENT_PATTERN = re.compile(
    r"^(?P<prefix>\s*(?:export\s+)?)"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<separator>\s*=\s*)(?P<value>.*)$"
)

SAFE_TOKEN_FIELDS = {
    "YTS_AUTH_ACCESS_TOKEN_TTL_SECONDS",
    "YTS_GATEWAY_TEXT_MAX_TOKENS",
}

PORTABLE_PATHS = {
    "YTS_LLAMA_SERVER_BIN": "desktop/vendor/llama.cpp/build/bin/llama-server",
    "YTS_LLAMA_MODEL": "desktop/vendor/llm-models/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    "YTS_IMAGEGEN_BIN": "desktop/vendor/stable-diffusion.cpp/build/bin/sd",
    "YTS_IMAGEGEN_DIFFUSION_MODEL": "desktop/vendor/sd-models/flux1-schnell-q4_k.gguf",
    "YTS_IMAGEGEN_VAE": "desktop/vendor/sd-models/ae-f16.gguf",
    "YTS_IMAGEGEN_CLIP_L": "desktop/vendor/sd-models/clip_l-q8_0.gguf",
    "YTS_IMAGEGEN_T5XXL": "desktop/vendor/sd-models/t5xxl_q4_k.gguf",
}

DATABASE_PLACEHOLDERS = {
    "YTS_DATABASE_URL": "postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME",
    "YTS_LANGGRAPH_CHECKPOINT_POSTGRES_DSN": "postgresql://USER:PASSWORD@HOST:5432/DBNAME",
}


class ExampleSyncError(RuntimeError):
    pass


def render_example(source: str) -> str:
    rendered: list[str] = []
    for line_number, line in enumerate(source.splitlines(keepends=True), start=1):
        body, ending = _split_line_ending(line)
        if not body.strip() or body.lstrip().startswith("#"):
            rendered.append(line)
            continue
        match = ASSIGNMENT_PATTERN.fullmatch(body)
        if match is None:
            raise ExampleSyncError(f"invalid env line {line_number}: expected NAME=VALUE")
        name = match.group("name")
        value = _sanitize_value(name, match.group("value"))
        rendered.append(
            f"{match.group('prefix')}{name}{match.group('separator')}{value}{ending}"
        )
    return "".join(rendered)


def sync_examples(root: Path) -> None:
    conf_dir = root / "conf"
    profiles = ("cloud", "local")
    rendered: dict[str, str] = {}
    for profile in profiles:
        source_path = conf_dir / f"{profile}.env"
        if not source_path.is_file():
            raise ExampleSyncError(f"missing required source config: {source_path}")
        try:
            rendered[profile] = render_example(source_path.read_text(encoding="utf-8"))
        except ExampleSyncError as exc:
            raise ExampleSyncError(f"{source_path}: {exc}") from exc

    temporary_paths: dict[str, Path] = {}
    try:
        for profile in profiles:
            target_path = conf_dir / f"{profile}.example.env"
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=conf_dir,
                prefix=f".{target_path.name}.",
                delete=False,
            ) as handle:
                handle.write(rendered[profile])
                handle.flush()
                os.fsync(handle.fileno())
                temporary_paths[profile] = Path(handle.name)
        for profile in profiles:
            os.replace(
                temporary_paths[profile],
                conf_dir / f"{profile}.example.env",
            )
    finally:
        for temporary_path in temporary_paths.values():
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sync_examples(root)
    print(root / "conf" / "cloud.example.env")
    print(root / "conf" / "local.example.env")
    return 0


def _sanitize_value(name: str, raw_value: str) -> str:
    value = _unquote(raw_value.strip())
    if _is_sensitive_name(name):
        return ""
    if name in DATABASE_PLACEHOLDERS:
        if value.startswith("sqlite"):
            return "sqlite+aiosqlite:///./yts_local.db"
        return DATABASE_PLACEHOLDERS[name]
    if name in PORTABLE_PATHS:
        return PORTABLE_PATHS[name]
    if _is_absolute_path(value):
        return "/path/to/value"
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc and (parsed.username is not None or parsed.password is not None):
        raise ExampleSyncError(f"credential-bearing URL cannot be published for {name}")
    return raw_value


def _is_sensitive_name(name: str) -> bool:
    if name in SAFE_TOKEN_FIELDS:
        return False
    upper_name = name.upper()
    return any(marker in upper_name for marker in ("KEY", "SECRET", "PASSWORD", "TOKEN"))


def _is_absolute_path(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1], line[-1]
    return line, ""


if __name__ == "__main__":
    raise SystemExit(main())
