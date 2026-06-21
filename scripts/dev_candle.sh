#!/usr/bin/env bash
# 启动本地 Candle 推理服务(Rust)。首次运行经 hf-hub 下载模型权重(默认 TinyLlama-1.1B-Chat GGUF)。
# 之后让服务端/桌面以 candle 后端跑:YTS_INFERENCE_BACKEND=candle
set -euo pipefail
cd "$(dirname "$0")/../desktop/candle-server"
# mac 默认启用 metal;CPU-only 机器用:cargo run --release --no-default-features
cargo run --release
