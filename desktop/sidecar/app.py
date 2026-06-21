"""Mac sidecar 入口 = 复用云端 FastAPI app,覆盖为本地 profile。

通过环境变量驱动 yts_core.config.Settings(env_prefix=YTS_):
本地 SQLite + 开自定义 skill + 关计费 + Candle 推理(经 Rust 出口/IPC)。
PyInstaller 打包此文件为 `yts-sidecar`;Tauri 作 externalBin 拉起(见 src-tauri/src/sidecar.rs)。
"""

from __future__ import annotations

import os

os.environ.setdefault("YTS_PROFILE", "local")
os.environ.setdefault("YTS_DATABASE_URL", "sqlite+aiosqlite:///./yts_local.db")
os.environ.setdefault("YTS_ALLOW_CUSTOM_SKILLS", "true")
os.environ.setdefault("YTS_BILLING_ENABLED", "false")
os.environ.setdefault("YTS_PHOENIX_ENABLED", "false")

import uvicorn  # noqa: E402
from yts_server.main import app  # noqa: E402


def main() -> None:
    port = int(os.environ.get("YTS_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
