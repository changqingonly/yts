#!/usr/bin/env bash
# 打包 macOS 桌面端(.app/.dmg)。产出两个 externalBin sidecar(infer-gateway、yts-sidecar,命名
# 需含 target triple,Tauri externalBin 约定)+ 跑 `tauri build`。llama-server/sd 二进制与模型权重
# 不在此打包(见 desktop/src-tauri/src/models.rs:首次运行时从 GitHub Releases/HuggingFace 下载)。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BINARIES="$ROOT/desktop/src-tauri/binaries"
TRIPLE="$(rustc -Vv | sed -n 's/host: //p')"
mkdir -p "$BINARIES"
echo "target triple: ${TRIPLE}"

echo ""
echo "== 1) 构建 infer-gateway(release) =="
(cd "$ROOT/desktop/infer-gateway" && cargo build --release)
cp "$ROOT/desktop/infer-gateway/target/release/infer-gateway" "$BINARIES/infer-gateway-${TRIPLE}"
echo "  -> ${BINARIES}/infer-gateway-${TRIPLE}"

echo ""
echo "== 2) 构建 yts-sidecar(PyInstaller)=="
bash "$ROOT/scripts/build_sidecar_macos.sh"

echo ""
echo "== 3) tauri build(.app/.dmg)=="
# 必须从 desktop/src-tauri(含 tauri.conf.json)起跑:tauri CLI 只向下找子目录里的
# tauri.conf.json,desktop/frontend 与 desktop/src-tauri 是同级目录,从 frontend 起跑会报
# "Couldn't recognize the current folder as a Tauri project"。beforeBuildCommand 的
# cwd 已在 tauri.conf.json 里显式指到 ../frontend,不依赖这里的当前目录。
(cd "$ROOT/desktop/src-tauri" && "$ROOT/desktop/frontend/node_modules/.bin/tauri" build)

echo ""
echo "✅ 完成。产物见 desktop/src-tauri/target/release/bundle/{macos,dmg}/。"
echo "   首次启动:设置 → 本地模型 → 下载(llama-server/sd 二进制 + 权重,来自 GitHub Releases / HuggingFace)。"
