#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "scripts/dev_gateway.sh has been retired." >&2
echo "Use: $ROOT/servctl components install && $ROOT/servctl start --profile local" >&2
exit 2
