#!/usr/bin/env bash
# 兼容入口:启动 FastAPI(开发热重载)。日常运维入口见 ./servctl。
set -euo pipefail
cd "$(dirname "$0")/.."
command=(./servctl start --profile "${YTS_PROFILE:-cloud}" --reload)
if [ -n "${YTS_PORT:-}" ]; then
  command+=(--port "$YTS_PORT")
fi
exec "${command[@]}"
