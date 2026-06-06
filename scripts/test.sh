#!/usr/bin/env bash
# test.sh - run the standard local verification suite.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$BACKEND/.uv-cache}"

GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[test]${NC} $1"; }

frontend_runner() {
  if command -v pnpm >/dev/null 2>&1; then
    echo "pnpm"
  else
    echo "npm"
  fi
}

log "Running backend tests..."
cd "$BACKEND"
uv run --extra dev pytest

runner="$(frontend_runner)"

if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "Missing frontend dependencies: run '$runner install' in frontend/ first." >&2
  exit 1
fi

log "Running frontend lint with $runner..."
cd "$FRONTEND"
"$runner" run lint

log "Running frontend build with $runner..."
"$runner" run build

log "Verification suite completed"
