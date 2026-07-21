#!/usr/bin/env bash
# 把 Python sidecar(复用 server app,本地 profile)打成 PyInstaller 可执行,供 Tauri 作 macOS sidecar。
# 产物命名需含 target triple(Tauri externalBin 约定),如 yts-sidecar-aarch64-apple-darwin。
set -euo pipefail
cd "$(dirname "$0")/.."
TRIPLE="$(rustc -Vv | sed -n 's/host: //p')"
echo "target triple: ${TRIPLE}"
uv run --group desktop-build pyinstaller desktop/sidecar/build_macos.spec --noconfirm
# 重命名为 Tauri externalBin 约定
OUT="desktop/src-tauri/binaries"
mkdir -p "${OUT}"
cp "dist/yts-sidecar" "${OUT}/yts-sidecar-${TRIPLE}" 2>/dev/null || \
  echo "TODO: 调整 dist 路径到 ${OUT}/yts-sidecar-${TRIPLE}"
echo "done (TODO: codesign + notarize,见 wiki Platform-Split)"
