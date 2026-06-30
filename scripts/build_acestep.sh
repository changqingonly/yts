#!/usr/bin/env bash
# 构建 acestep.cpp(ACE-Step 1.5,GGML/Metal,纯 C++)并下载 GGUF 模型。
# 之后让 candle-server 用它作 audiogen producer:
#   export YTS_AUDIOGEN_CMD="<acestep-bin> --prompt {prompt} --seconds {seconds} --out {out} ..."
# 注:实际 CLI 参数以 acestep.cpp 仓库 README 为准;{prompt}{seconds}{out} 是 candle-server 的占位约定。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/desktop/vendor"
mkdir -p "$VENDOR"
cd "$VENDOR"

if [ ! -d acestep.cpp ]; then
  git clone https://github.com/ServeurpersoCom/acestep.cpp.git
fi
cd acestep.cpp

# Metal 加速(Apple Silicon)。具体 CMake 选项以仓库 README 为准。
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON
cmake --build build -j

echo ""
echo "=== 下一步(手动) ==="
echo "1) 下载 ACE-Step-1.5 GGUF 模型(建议 0.6B LM + turbo DiT 起步):"
echo "   huggingface-cli download Serveurperso/ACE-Step-1.5-GGUF --local-dir $VENDOR/acestep-models"
echo "2) 设置 producer 命令(参数名以 acestep.cpp README 为准),例如:"
echo "   export YTS_AUDIOGEN_CMD=\"$VENDOR/acestep.cpp/build/acestep --model $VENDOR/acestep-models/<lm.gguf> --dit <dit.gguf> --prompt {prompt} --seconds {seconds} --out {out}\""
echo "3) 重启 candle-server,前端音乐页即用真 ACE-Step 流式播放(契约/前端零改动)。"
