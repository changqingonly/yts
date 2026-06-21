#!/usr/bin/env bash
# 安装 uv(若未安装)。优先 brew,回退官方安装脚本。
set -euo pipefail
if command -v uv >/dev/null 2>&1; then
  echo "uv already installed: $(uv --version)"; exit 0
fi
if command -v brew >/dev/null 2>&1; then
  brew install uv
else
  curl -LsSf https://astral.sh/uv/install.sh | sh
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.zshrc" || true
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version
