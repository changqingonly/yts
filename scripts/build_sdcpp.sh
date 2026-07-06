#!/usr/bin/env bash
# 一条命令搞定:构建 stable-diffusion.cpp(GGML/Metal)+ 自动下载 GGUF 模型 + 生成 producer 配置。
# 跑完直接 `bash scripts/dev_gateway.sh`,前端图片生成即用真 stable-diffusion.cpp,零手动步骤。
#
# 默认模型:FLUX.1-schnell(Apache-2.0,可商用)全 GGUF,来自 ungated 仓 Green-Sky/flux.1-schnell-GGUF。
# 覆盖:SD_MODEL_REPO / SD_DIFFUSION / SD_VAE / SD_CLIP / SD_T5 / SD_STEPS 等环境变量。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/desktop/vendor"
SRC="$VENDOR/stable-diffusion.cpp"
MODELS="$VENDOR/sd-models"
ENVFILE="$VENDOR/imagegen.env"
mkdir -p "$VENDOR" "$MODELS"

# ---- 模型清单(可用 env 覆盖)----
SD_MODEL_REPO="${SD_MODEL_REPO:-Green-Sky/flux.1-schnell-GGUF}"
SD_DIFFUSION="${SD_DIFFUSION:-flux1-schnell-q4_k.gguf}"
SD_VAE="${SD_VAE:-ae-f16.gguf}"
SD_CLIP="${SD_CLIP:-clip_l-q8_0.gguf}"
SD_T5="${SD_T5:-t5xxl_q4_k.gguf}"
SD_STEPS="${SD_STEPS:-4}"          # schnell 4 步即可
SD_CFG="${SD_CFG:-1.0}"            # schnell cfg=1.0
SD_SAMPLER="${SD_SAMPLER:-euler}"

# ---- 1) 构建 stable-diffusion.cpp(Metal)----
if [ ! -d "$SRC" ]; then
  git clone --recursive https://github.com/leejet/stable-diffusion.cpp.git "$SRC"
fi
cd "$SRC"
cmake -B build -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build build -j --config Release
SD_BIN="$SRC/build/bin/sd"
[ -x "$SD_BIN" ] || SD_BIN="$SRC/build/sd"   # 布局兜底
echo "sd binary: $SD_BIN"

# ---- 2) 自动下载模型(ungated,免登录;已存在则跳过,支持断点续传)----
dl() {  # dl <file>
  local f="$1" dst="$MODELS/$1"
  local url="https://huggingface.co/${SD_MODEL_REPO}/resolve/main/${f}?download=true"
  if [ -s "$dst" ]; then echo "  ✓ 已存在 $f"; return; fi
  echo "  ↓ 下载 $f ..."
  curl -fL -C - --retry 3 -o "$dst" "$url"
}
echo "下载模型到 $MODELS (仓库: $SD_MODEL_REPO)"
dl "$SD_DIFFUSION"; dl "$SD_VAE"; dl "$SD_CLIP"; dl "$SD_T5"

# ---- 3) 生成 producer 配置(infer-gateway 读 YTS_IMAGEGEN_CMD)----
cat > "$ENVFILE" <<EOF
# 由 scripts/build_sdcpp.sh 自动生成。dev_gateway.sh 会自动 source 本文件。
export YTS_IMAGEGEN_CMD='${SD_BIN} --diffusion-model ${MODELS}/${SD_DIFFUSION} --vae ${MODELS}/${SD_VAE} --clip_l ${MODELS}/${SD_CLIP} --t5xxl ${MODELS}/${SD_T5} -p {prompt} -o {out} -W {width} -H {height} --steps ${SD_STEPS} --cfg-scale ${SD_CFG} --sampling-method ${SD_SAMPLER}'
EOF

echo ""
echo "✅ 完成。图片生成已就绪(配置写入 $ENVFILE)。"
echo "   启动:bash scripts/dev_gateway.sh   # 会自动加载上面的 YTS_IMAGEGEN_CMD"
echo "   换模型:设 SD_MODEL_REPO/SD_DIFFUSION 等 env 后重跑本脚本(如 SDXL / Qwen-Image)。"
