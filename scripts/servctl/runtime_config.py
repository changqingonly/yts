from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import ServctlError

FRONTEND_RUNTIME_CONFIG_URL = "/runtime-config.json"
RUNTIME_CONFIG_URL_ENV = "VITE_YTS_RUNTIME_CONFIG_URL"


def frontend_runtime_config(profile: str) -> dict[str, object]:
    if profile not in {"local", "cloud"}:
        raise ServctlError(f"unsupported frontend runtime profile: {profile}")
    return {
        "schemaVersion": 1,
        "profile": profile,
        "defaultTarget": profile,
        "targets": {
            "local": {
                "apiBase": "http://127.0.0.1:8765",
                "musicWsBase": "ws://127.0.0.1:8799",
            },
            "cloud": {
                "apiBase": "http://127.0.0.1:8000",
                "musicWsBase": "ws://127.0.0.1:8000",
            },
        },
    }


def write_frontend_runtime_config(root: Path, profile: str) -> Path:
    dist_dir = root / "desktop" / "frontend" / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    destination = dist_dir / "runtime-config.json"
    payload = json.dumps(frontend_runtime_config(profile), ensure_ascii=False, indent=2) + "\n"

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=dist_dir,
            prefix=".runtime-config.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        os.replace(temp_path, destination)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination


__all__ = [
    "FRONTEND_RUNTIME_CONFIG_URL",
    "RUNTIME_CONFIG_URL_ENV",
    "frontend_runtime_config",
    "write_frontend_runtime_config",
]
