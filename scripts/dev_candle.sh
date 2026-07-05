#!/usr/bin/env bash
# 启动本地 Candle 推理服务(Rust)。首次运行经 hf-hub 下载模型权重(默认 TinyLlama-1.1B-Chat GGUF)。
# 之后让服务端/桌面以本地产品后端跑:YTS_INFERENCE_BACKEND=local
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# 若已跑过 build_sdcpp.sh,自动加载图片生成 producer 配置(YTS_IMAGEGEN_CMD)
IMG_ENV="$HERE/../desktop/vendor/imagegen.env"
if [ -f "$IMG_ENV" ]; then
  # shellcheck disable=SC1090
  source "$IMG_ENV"
  echo "已加载图片生成 producer:${YTS_IMAGEGEN_CMD%% *} ..."
fi
cd "$HERE/../desktop/candle-server"
# mac 默认启用 metal;CPU-only 机器用:cargo run --release --no-default-features
cargo run --release
