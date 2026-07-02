#!/usr/bin/env bash
# Bootstrap customer-machine runtime into this project directory.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS_DIR="${ROOT}/.tools"
UV_HOME="${TOOLS_DIR}/uv"
NODE_HOME="${TOOLS_DIR}/node"
NODE_VERSION="${YTS_NODE_VERSION:-v24.18.0}"

mkdir -p "${TOOLS_DIR}"

require_command() {
  local name="$1"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo "install: required command not found: ${name}" >&2
    exit 1
  fi
}

detect_node_platform() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"

  case "${os}" in
    Darwin) os="darwin" ;;
    Linux) os="linux" ;;
    *) echo "install: unsupported OS for bundled Node: ${os}" >&2; exit 1 ;;
  esac

  case "${arch}" in
    arm64|aarch64) arch="arm64" ;;
    x86_64|amd64) arch="x64" ;;
    *) echo "install: unsupported CPU architecture for bundled Node: ${arch}" >&2; exit 1 ;;
  esac

  printf '%s-%s\n' "${os}" "${arch}"
}

install_uv() {
  require_command curl
  echo "install: installing uv into ${UV_HOME}"
  mkdir -p "${UV_HOME}"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="${UV_HOME}" sh
}

install_node() {
  require_command curl
  require_command tar
  local platform archive url tmp_dir extracted
  platform="$(detect_node_platform)"
  archive="node-${NODE_VERSION}-${platform}.tar.xz"
  url="https://nodejs.org/dist/${NODE_VERSION}/${archive}"
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' RETURN

  echo "install: downloading Node ${NODE_VERSION} for ${platform}"
  curl -fL "${url}" -o "${tmp_dir}/${archive}"
  rm -rf "${NODE_HOME}"
  mkdir -p "${NODE_HOME}"
  tar -xJf "${tmp_dir}/${archive}" -C "${NODE_HOME}" --strip-components=1
  extracted="${NODE_HOME}/bin/node"
  if [ ! -x "${extracted}" ]; then
    echo "install: Node install did not produce ${extracted}" >&2
    exit 1
  fi
}

export PATH="${UV_HOME}:${NODE_HOME}/bin:${PATH}"
export UV_PYTHON_INSTALL_DIR="${TOOLS_DIR}/python"
export UV_PROJECT_ENVIRONMENT="${ROOT}/.venv"

install_uv
install_node

cd "${ROOT}"
uv python install
uv venv "${ROOT}/.venv"
uv sync --locked

cd "${ROOT}/desktop/frontend"
npm ci

echo "install: complete"
