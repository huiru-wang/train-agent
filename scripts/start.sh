#!/usr/bin/env bash
# start.sh — 启动 train-agent 全部服务（后端API + LangGraph + 前端）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOGS="$ROOT/logs"

export TZ=Asia/Shanghai
export UV_CACHE_DIR="${UV_CACHE_DIR:-$BACKEND/.uv-cache}"
mkdir -p "$LOGS"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[start]${NC} $1"; }

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

# --- Start Backend API ---
log "启动后端 API (port 8000)..."
cd "$BACKEND"
nohup uv run uvicorn src.api.routes:app --host 0.0.0.0 --port 8000 --reload > "$LOGS/backend.log" 2>&1 &
echo $! > "$LOGS/backend.pid"

# --- Start LangGraph ---
log "启动 LangGraph (port 2024)..."
cd "$BACKEND"
nohup env NO_COLOR=1 uv run langgraph dev --port 2024 --no-browser > "$LOGS/langgraph.log" 2>&1 &
echo $! > "$LOGS/langgraph.pid"

# --- Start Frontend ---
log "启动前端 (port 3000, runner: $FRONTEND_RUNNER)..."
cd "$FRONTEND"
nohup "$FRONTEND_RUNNER" run dev > "$LOGS/frontend.log" 2>&1 &
echo $! > "$LOGS/frontend.pid"

sleep 2

# --- Verify ---
echo ""
log "========== 服务状态 =========="
FAILED=0

check_port() {
  local name=$1 port=$2 pid_file=$3 log_file=$4
  if lsof -ti:$port > /dev/null 2>&1; then
    log "✅ $name (port $port) — 运行中"
  else
    local pid=""
    if [ -f "$pid_file" ]; then
      pid="$(cat "$pid_file")"
    fi

    if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
      log "⏳ $name (port $port) — 启动中，请稍候..."
    else
      log "❌ $name (port $port) — 启动失败"
      if [ -f "$log_file" ]; then
        log "最近日志: $log_file"
        tail -n 40 "$log_file"
      fi
      FAILED=1
    fi
  fi
}

check_port "后端 API" 8000 "$LOGS/backend.pid" "$LOGS/backend.log"
check_port "LangGraph" 2024 "$LOGS/langgraph.pid" "$LOGS/langgraph.log"
check_port "前端" 3000 "$LOGS/frontend.pid" "$LOGS/frontend.log"

echo ""
log "日志文件:"
log "  后端:      tail -f $LOGS/backend.log"
log "  LangGraph: tail -f $LOGS/langgraph.log"
log "  前端:      tail -f $LOGS/frontend.log"
echo ""
log "访问: http://localhost:3000"

if [ "$FAILED" -ne 0 ]; then
  exit 1
fi
