#!/usr/bin/env bash
# 桌面端开发(Mac):启动 Vite + Tauri。首次需 npm install。
set -euo pipefail
cd "$(dirname "$0")/../desktop/frontend"
[ -d node_modules ] || npm install
npm run tauri:dev
