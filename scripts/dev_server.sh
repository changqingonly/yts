#!/usr/bin/env bash
# 兼容入口:启动 FastAPI(开发热重载)。日常运维入口见 ./servctl。
set -euo pipefail
cd "$(dirname "$0")/.."
exec ./servctl start --profile "${YTS_PROFILE:-cloud}" --port "${YTS_PORT:-8000}" --reload
