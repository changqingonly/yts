#!/usr/bin/env bash
# 启动本地 GGML 推理网关(Rust)。文本→llama.cpp、图片→sd.cpp、音乐→acestep.cpp。
# 网关按下方自动加载的 producer 配置对接各 GGML 二进制;上层用 YTS_INFERENCE_BACKEND=local。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENDOR="$HERE/../desktop/vendor"

# 自动加载各模态 producer 配置(跑过对应 build_*.sh 后即存在):
#   llamacpp.env → YTS_LLAMA_CMD/BASE_URL(文本);imagegen.env → YTS_IMAGEGEN_CMD(图片)
for envf in llamacpp.env imagegen.env; do
  if [ -f "$VENDOR/$envf" ]; then
    # shellcheck disable=SC1090
    source "$VENDOR/$envf"
    echo "已加载 $envf"
  fi
done
[ -n "${YTS_LLAMA_CMD:-}" ] && echo "文本 producer:llama-server(${YTS_LLAMA_CMD##*/})"
[ -n "${YTS_IMAGEGEN_CMD:-}" ] && echo "图片 producer:${YTS_IMAGEGEN_CMD%% *}"

cd "$HERE/../desktop/candle-server"
cargo run --release
