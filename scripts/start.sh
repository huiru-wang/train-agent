#!/usr/bin/env bash
# start.sh — 启动 train-agent 全部服务（后端API + LangGraph + 前端）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOGS="$ROOT/logs"
TMP="$ROOT/tmp"

export TZ=Asia/Shanghai
export UV_CACHE_DIR="${UV_CACHE_DIR:-$BACKEND/.uv-cache}"
mkdir -p "$LOGS" "$TMP"

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
  log "安装前端依赖..."
  cd "$FRONTEND"
  "$FRONTEND_RUNNER" install
  cd "$ROOT"
fi

# --- Start Backend API ---
log "启动后端 API (port 8000)..."
cd "$BACKEND"
nohup uv run uvicorn src.api.routes:app --host 0.0.0.0 --port 8000 --reload --reload-exclude '.venv' > "$LOGS/backend.log" 2>&1 &
echo $! > "$TMP/backend.pid"

# --- Start LangGraph ---
log "启动 LangGraph (port 2024)..."
cd "$BACKEND"
nohup env NO_COLOR=1 uv run langgraph dev --port 2024 --no-browser --no-reload > "$LOGS/langgraph.log" 2>&1 &
echo $! > "$TMP/langgraph.pid"

# --- Start Frontend ---
log "启动前端 (port 3000, runner: $FRONTEND_RUNNER)..."
cd "$FRONTEND"
# pnpm 10+ 需要 Node.js v22+。若 nvm 可用则先切换，避免 ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING。
if [ -f "$HOME/.nvm/nvm.sh" ]; then
  export NVM_DIR="$HOME/.nvm"
  # shellcheck source=/dev/null
  source "$NVM_DIR/nvm.sh" --no-use
  if nvm ls v22 >/dev/null 2>&1; then
    nvm use v22 >/dev/null 2>&1 || true
    log "已切换至 Node.js $(node --version) 以兼容 pnpm"
  fi
fi
nohup "$FRONTEND_RUNNER" run dev > "$LOGS/frontend.log" 2>&1 &
echo $! > "$TMP/frontend.pid"

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

check_port "后端 API" 8000 "$TMP/backend.pid" "$LOGS/backend.log"
check_port "LangGraph" 2024 "$TMP/langgraph.pid" "$LOGS/langgraph.log"
check_port "前端" 3000 "$TMP/frontend.pid" "$LOGS/frontend.log"

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
