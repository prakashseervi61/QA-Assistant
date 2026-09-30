#!/usr/bin/env bash
# ============================================================================
#  Start the QA Assistant (FastAPI + Vite) in the background.
#
#  Both servers are detached with nohup, so this script returns immediately and
#  leaves no terminals attached to the desktop. It waits until the services are
#  actually ready, opens the browser, and records PIDs for stop_all.sh.
#
#  Run ./scripts/start_all.sh to start, ./scripts/stop_all.sh to stop.
# ============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REACT_DIR="$PROJECT_ROOT/src/presentation/react"
RUN_DIR="$PROJECT_ROOT/.run"
LOG_DIR="$RUN_DIR/logs"

API_PORT=8000
WEB_PORT=3000
APP_URL="http://localhost:$WEB_PORT"
API_URL="http://localhost:$API_PORT"

mkdir -p "$LOG_DIR"

echo "============================================================"
echo "  QA Assistant - starting services"
echo "============================================================"
echo

# --- stop anything left over from a previous run ---------------------------
"$(dirname "${BASH_SOURCE[0]}")/stop_all.sh" --quiet || true
echo

# --- resolve the uvicorn entrypoint ----------------------------------------
if command -v uvicorn >/dev/null 2>&1; then
    UVICORN_CMD=(uvicorn)
else
    UVICORN_CMD=("$(command -v python3 || command -v python)" -m uvicorn)
fi

# --- backend ---------------------------------------------------------------
# No --reload here on purpose: it re-imports the whole app in a child process,
# roughly doubling startup, and leaves a grandchild the PID file does not
# track. Stop and start to pick up backend code changes.
echo "Starting API  (port $API_PORT)..."
cd "$PROJECT_ROOT"
nohup "${UVICORN_CMD[@]}" \
    src.presentation.api.app:create_app \
    --factory --host 0.0.0.0 --port "$API_PORT" \
    >"$LOG_DIR/api.out.log" 2>"$LOG_DIR/api.err.log" &
echo "$!" >"$RUN_DIR/api.pid"

# --- frontend (started immediately, not gated on the API) ------------------
echo "Starting web UI  (port $WEB_PORT)..."
cd "$REACT_DIR"
nohup npm run dev -- --host 127.0.0.1 --port "$WEB_PORT" \
    >"$LOG_DIR/web.out.log" 2>"$LOG_DIR/web.err.log" &
echo "$!" >"$RUN_DIR/web.pid"

# --- wait for the web UI, then open the browser ---------------------------
# Vite comes up in a second or two, so this is the gate that matters for
# "how fast does the browser open". The API is reported on separately below.
echo "Waiting for the web UI..."
web_ready=0
for _ in $(seq 1 45); do
    if curl -fsS --max-time 2 "$APP_URL" >/dev/null 2>&1; then
        web_ready=1
        break
    fi
    sleep 1
done

if [ "$web_ready" -eq 0 ]; then
    echo "[!] The web UI did not answer in 45s. See $LOG_DIR/web.err.log"
fi

# --- open the browser as soon as the page is servable ----------------------
if command -v open >/dev/null 2>&1; then
    open "$APP_URL"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$APP_URL" >/dev/null 2>&1
else
    echo "[i] Could not find a browser opener - open $APP_URL yourself."
fi

# --- report API health (informational, never blocks the browser) ----------
api_ready=0
for _ in $(seq 1 90); do
    if curl -fsS --max-time 2 "$API_URL/api/health" >/dev/null 2>&1; then
        api_ready=1
        break
    fi
    sleep 1
done

if [ "$api_ready" -eq 1 ]; then
    echo "[ok] API ready  -  $API_URL"
else
    echo "[!] API still starting - see $LOG_DIR/api.err.log"
fi

cat <<EOF

============================================================
  Running in the background - no terminals left open.

  App       $APP_URL
  API       $API_URL
  API Docs  $API_URL/docs
  Logs      $LOG_DIR

  Stop with ./scripts/stop_all.sh
============================================================

EOF
