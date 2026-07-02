#!/usr/bin/env bash
# 兼容入口:完整安装客户机运行环境到当前项目目录。
set -euo pipefail
cd "$(dirname "$0")/.."
exec ./install "$@"
