#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
PORT="${PORT:-8000}"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

PORT="${PORT:-8000}"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
PYTHON_BIN="$ROOT_DIR/.venv/Scripts/python.exe"

if [[ ! -x "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

echo "=== Ollama MCP HTTP Server ==="
echo "Port   : $PORT"
echo "Ollama : $OLLAMA_HOST"
if [[ -n "${API_KEY:-}" ]]; then
  echo "APIKey : ${API_KEY}"
else
  echo "APIKey : (none - WARNING: open access!)"
fi
echo

find_cloudflared() {
  local candidates=(
    "cloudflared"
    "/c/Program Files (x86)/cloudflared/cloudflared.exe"
    "/c/Program Files/cloudflared/cloudflared.exe"
    "C:/Program Files (x86)/cloudflared/cloudflared.exe"
    "C:/Program Files/cloudflared/cloudflared.exe"
  )

  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

CF_BIN=""
if CF_BIN="$(find_cloudflared)"; then
  echo "Starting Cloudflare Tunnel in background..."
  CF_LOG="$ROOT_DIR/cloudflared.err.log"
  : > "$CF_LOG"
  "$CF_BIN" tunnel --url "http://localhost:$PORT" >"$ROOT_DIR/cloudflared.out.log" 2>"$CF_LOG" &
  CF_PID=$!

  TUNNEL_URL=""
  for _ in {1..20}; do
    sleep 1
    TUNNEL_URL="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$CF_LOG" | tail -n 1 || true)"
    if [[ -n "$TUNNEL_URL" ]]; then
      break
    fi
  done

  if [[ -n "$TUNNEL_URL" ]]; then
    echo
    echo "[CHAT UI]     $TUNNEL_URL/"
    echo "[REST API]    $TUNNEL_URL/api/chat"
    echo "[MCP URL]     $TUNNEL_URL/mcp"
    echo "[Tunnel PID]  $CF_PID"
    echo
    cat <<JSON
Claude/Codex MCP config:
{
  "mcpServers": {
    "ollama-remote": {
      "type": "http",
      "url": "$TUNNEL_URL/mcp",
      "headers": { "X-API-Key": "${API_KEY:-}" }
    }
  }
}
JSON
  else
    echo "Tunnel started but URL was not detected yet."
    echo "Check: $CF_LOG"
  fi
else
  echo "cloudflared not found. Install it with:"
  echo "  winget install Cloudflare.cloudflared"
fi

echo
echo "[LOCAL UI]    http://localhost:$PORT/"
echo "[LOCAL API]   http://localhost:$PORT/api/chat"
echo "[LOCAL MCP]   http://localhost:$PORT/mcp"
echo
echo "Starting MCP server... (Ctrl+C to stop)"
echo

exec "$PYTHON_BIN" "$ROOT_DIR/server.py" http
