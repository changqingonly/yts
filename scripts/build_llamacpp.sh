#!/usr/bin/env bash
# 一条命令搞定文本:构建 llama.cpp(GGML/Metal)+ 自动下载 GGUF 模型 + 生成 producer 配置。
# 跑完直接 `bash scripts/dev_gateway.sh`(网关会 spawn 常驻 llama-server 并代理 /candle/text),零手动。
#
# 默认模型:Qwen2.5-7B-Instruct(Apache-2.0,ungated,48GB M4 宽裕)。单文件 Q4_K_M(~4.7GB)。
# 覆盖:LLM_MODEL_REPO / LLM_MODEL_FILE / LLM_CTX / LLM_PORT 环境变量。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/desktop/vendor"
SRC="$VENDOR/llama.cpp"
MODELS="$VENDOR/llm-models"
ENVFILE="$VENDOR/llamacpp.env"
mkdir -p "$VENDOR" "$MODELS"

LLM_MODEL_REPO="${LLM_MODEL_REPO:-bartowski/Qwen2.5-7B-Instruct-GGUF}"
LLM_MODEL_FILE="${LLM_MODEL_FILE:-Qwen2.5-7B-Instruct-Q4_K_M.gguf}"
LLM_CTX="${LLM_CTX:-4096}"
LLM_PORT="${LLM_PORT:-8080}"

# ---- 1) 构建 llama.cpp(Metal)----
if [ ! -d "$SRC" ]; then
  git clone https://github.com/ggml-org/llama.cpp.git "$SRC"
fi
cd "$SRC"
cmake -B build -DGGML_METAL=ON -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build build -j --config Release --target llama-server
LLAMA_BIN="$SRC/build/bin/llama-server"
[ -x "$LLAMA_BIN" ] || LLAMA_BIN="$SRC/build/llama-server"
echo "llama-server: $LLAMA_BIN"

# ---- 2) 自动下载模型(ungated,免登录;已存在则跳过,支持断点续传)----
dst="$MODELS/$LLM_MODEL_FILE"
if [ -s "$dst" ]; then
  echo "  ✓ 已存在 $LLM_MODEL_FILE"
else
  echo "  ↓ 下载 $LLM_MODEL_FILE ..."
  curl -fL -C - --retry 3 -o "$dst" \
    "https://huggingface.co/${LLM_MODEL_REPO}/resolve/main/${LLM_MODEL_FILE}?download=true"
fi

# ---- 3) 生成 producer 配置(网关按 YTS_LLAMA_CMD spawn 常驻 llama-server)----
cat > "$ENVFILE" <<EOF
# 由 scripts/build_llamacpp.sh 自动生成。dev_gateway.sh 会自动 source 本文件。
export YTS_LLAMA_BASE_URL='http://127.0.0.1:${LLM_PORT}'
export YTS_LLAMA_CMD='${LLAMA_BIN} -m ${dst} --host 127.0.0.1 --port ${LLM_PORT} -c ${LLM_CTX} -ngl 99 --log-disable'
EOF

echo ""
echo "✅ 完成。文本已就绪(llama.cpp,配置写入 $ENVFILE)。"
echo "   启动:bash scripts/dev_gateway.sh   # 网关自动 spawn 常驻 llama-server 并代理"
echo "   换模型:设 LLM_MODEL_REPO/LLM_MODEL_FILE 后重跑(如 Qwen3-8B / Llama3.x)。"
