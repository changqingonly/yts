#!/usr/bin/env bash
# 启动本地 GGML 推理网关(Rust)。文本→llama.cpp、图片→sd.cpp、音乐→acestep.cpp。
# 网关按下方自动加载的 producer 配置对接各 GGML 二进制;上层用 YTS_INFERENCE_BACKEND=local。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENDOR="$HERE/../desktop/vendor"

ROOT="$(cd "$HERE/.." && pwd)"
set -a
source "$ROOT/conf/local.env"
set +a
resolve() { [[ "$1" = /* ]] && printf '%s' "$1" || printf '%s/%s' "$ROOT" "$1"; }
export YTS_LLAMA_BASE_URL="http://127.0.0.1:${YTS_LLAMA_PORT:-18080}"
export YTS_LLAMA_CMD="$(resolve "$YTS_LLAMA_SERVER_BIN") -m $(resolve "$YTS_LLAMA_MODEL") --host 127.0.0.1 --port ${YTS_LLAMA_PORT:-18080} -c ${YTS_LLAMA_CTX:-4096} -ngl ${YTS_LLAMA_GPU_LAYERS:-99} --log-disable"
export YTS_IMAGEGEN_CMD="$(resolve "$YTS_IMAGEGEN_BIN") --diffusion-model $(resolve "$YTS_IMAGEGEN_DIFFUSION_MODEL") --vae $(resolve "$YTS_IMAGEGEN_VAE") --clip_l $(resolve "$YTS_IMAGEGEN_CLIP_L") --t5xxl $(resolve "$YTS_IMAGEGEN_T5XXL") -p {prompt} -o {out} -W {width} -H {height} --steps 4 --cfg-scale 1.0 --sampling-method euler"
[ -n "${YTS_LLAMA_CMD:-}" ] && echo "文本 producer:llama-server(${YTS_LLAMA_CMD##*/})"
[ -n "${YTS_IMAGEGEN_CMD:-}" ] && echo "图片 producer:${YTS_IMAGEGEN_CMD%% *}"

cd "$HERE/../desktop/infer-gateway"
cargo run --release
