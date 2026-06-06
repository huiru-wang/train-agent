#!/usr/bin/env bash
# dev.sh - run all train-agent services in the foreground.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOGS="$ROOT/logs"

export TZ=Asia/Shanghai
export UV_CACHE_DIR="${UV_CACHE_DIR:-$BACKEND/.uv-cache}"
mkdir -p "$LOGS"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[dev]${NC} $1"; }
warn() { echo -e "${YELLOW}[dev]${NC} $1"; }

require_cmd() {
  local name=$1
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required command: $name" >&2
    echo "Run ./scripts/doctor.sh for setup details." >&2
    exit 1
  fi
}

frontend_runner() {
  if command -v pnpm >/dev/null 2>&1; then
    echo "pnpm"
  elif command -v npm >/dev/null 2>&1; then
    echo "npm"
  else
    echo ""
  fi
}

require_cmd uv
require_cmd node

FRONTEND_RUNNER="$(frontend_runner)"
if [ -z "$FRONTEND_RUNNER" ]; then
  echo "Missing frontend package manager: install pnpm or npm." >&2
  exit 1
fi

if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "Missing frontend dependencies: run '$FRONTEND_RUNNER install' in frontend/ first." >&2
  echo "Run ./scripts/doctor.sh for setup details." >&2
  exit 1
fi

PIDS=()

cleanup() {
  warn "stopping services..."
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -TERM "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait >/dev/null 2>&1 || true
  warn "all services stopped"
}
trap cleanup INT TERM EXIT

log "starting backend API on http://localhost:8000"
(
  cd "$BACKEND"
  uv run uvicorn src.api.routes:app --host 0.0.0.0 --port 8000 --reload
) > "$LOGS/backend.log" 2>&1 &
pid="$!"
PIDS+=("$pid")
echo "$pid" > "$LOGS/backend.pid"

log "starting LangGraph on http://localhost:2024"
(
  cd "$BACKEND"
  NO_COLOR=1 uv run langgraph dev --port 2024 --no-browser
) > "$LOGS/langgraph.log" 2>&1 &
pid="$!"
PIDS+=("$pid")
echo "$pid" > "$LOGS/langgraph.pid"

log "starting frontend on http://localhost:3000"
(
  cd "$FRONTEND"
  "$FRONTEND_RUNNER" run dev
) > "$LOGS/frontend.log" 2>&1 &
pid="$!"
PIDS+=("$pid")
echo "$pid" > "$LOGS/frontend.pid"

sleep 3

log "logs:"
log "  backend:   tail -f $LOGS/backend.log"
log "  langgraph: tail -f $LOGS/langgraph.log"
log "  frontend:  tail -f $LOGS/frontend.log"
log "open http://localhost:3000"
log "press Ctrl-C to stop all services"

while true; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      warn "one service exited; see logs for details"
      exit 1
    fi
  done
  sleep 2
done
