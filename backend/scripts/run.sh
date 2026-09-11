#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
exec python -m app.main
