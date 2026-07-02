"""
Mac sidecar 入口 = 复用云端 FastAPI app,覆盖为本地 profile。

配置由 yts_core.config 读取项目 conf/local.env;这里只设置默认 profile。
PyInstaller 打包此文件为 `yts-sidecar`;Tauri 作 externalBin 拉起(见 src-tauri/src/sidecar.rs)。
"""

from __future__ import annotations

import os

os.environ.setdefault("YTS_PROFILE", "local")

import uvicorn  # noqa: E402
from yts_server.main import app  # noqa: E402


def main() -> None:
    port = int(os.environ.get("YTS_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
