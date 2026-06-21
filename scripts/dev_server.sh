#!/usr/bin/env bash
# 启动云实现 FastAPI(开发热重载)。
set -euo pipefail
cd "$(dirname "$0")/.."
export YTS_PROFILE="${YTS_PROFILE:-cloud}"
uv run uvicorn yts_server.main:app --reload --host 127.0.0.1 --port "${YTS_PORT:-8000}"
