#!/usr/bin/env bash
# 把 Python sidecar(复用 server app,本地 profile)打成 PyInstaller 可执行,供 Tauri 作 macOS sidecar。
# 产物命名需含 target triple(Tauri externalBin 约定),如 yts-sidecar-aarch64-apple-darwin。
set -euo pipefail
cd "$(dirname "$0")/.."
TRIPLE="$(rustc -Vv | sed -n 's/host: //p')"
echo "target triple: ${TRIPLE}"
uv run pyinstaller desktop/sidecar/build_macos.spec --noconfirm
# 重命名为 Tauri externalBin 约定
OUT="desktop/src-tauri/bin"
mkdir -p "${OUT}"
if [ ! -x "dist/yts-sidecar" ]; then
  echo "missing PyInstaller output: dist/yts-sidecar" >&2
  exit 1
fi
cp "dist/yts-sidecar" "${OUT}/yts-sidecar-${TRIPLE}"
echo "done: ${OUT}/yts-sidecar-${TRIPLE}"
