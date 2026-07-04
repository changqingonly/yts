#!/usr/bin/env bash
# 构建 stable-diffusion.cpp(leejet,GGML/Metal)并提示下载 GGUF 模型。
# 之后让 candle-server 用它作图像 producer:
#   export YTS_IMAGEGEN_CMD="<sd-bin> ... -p {prompt} -o {out} -W {width} -H {height} --steps {steps}"
# 注:实际 CLI 参数以 stable-diffusion.cpp README 为准;{prompt}{out}{width}{height}{steps} 是 candle-server 占位约定。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/desktop/vendor"
mkdir -p "$VENDOR"
cd "$VENDOR"

if [ ! -d stable-diffusion.cpp ]; then
  git clone --recursive https://github.com/leejet/stable-diffusion.cpp.git
fi
cd stable-diffusion.cpp

# Apple Silicon Metal 加速。具体选项以仓库 README 为准。
cmake -B build -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --config Release

cat <<EOF

=== 下一步(手动) ===
1) 下载 GGUF 模型(48GB M4 推荐,授权可商用优先):
   # FLUX.2-klein 4B(Apache-2.0,~13GB,质量/速度平衡):
   #   diffusion_model / clip / t5 / vae 各组件 GGUF,见 HF 上 leejet/相关仓库
   # 或 Qwen-Image(Apache-2.0,图内文字/中文最佳)/ SDXL(LoRA 生态)
   # FLUX.1-dev 全 FP16(顶级质量,48GB 够;但 dev 授权禁止售卖产出)
2) 设置 producer 命令(参数名以 sd.cpp README 为准),例如:
   export YTS_IMAGEGEN_CMD="$VENDOR/stable-diffusion.cpp/build/bin/sd \\
     --diffusion-model <flux.gguf> --clip_l <clip.gguf> --t5xxl <t5.gguf> --vae <vae.gguf> \\
     -p {prompt} -o {out} -W {width} -H {height} --steps {steps} --cfg-scale 1.0 --sampling-method euler"
3) 重启 candle-server → 前端图片生成即用真 stable-diffusion.cpp(端点/前端零改动)。
EOF
