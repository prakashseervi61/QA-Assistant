#!/usr/bin/env bash
# ============================================================================
#  Stop every process belonging to the QA Assistant.
#
#  Kills, in order:
#    1. the launcher PIDs recorded in .run/api.pid and .run/web.pid
#    2. the whole process group of each (so --reload children die too)
#    3. any remaining listener on the API port (8000) and web port (3000)
#       -- catches orphans from earlier sessions that wrote no PID file
#
#  Pass --quiet to suppress output (used by start_all.sh).
# ============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$PROJECT_ROOT/.run"

API_PORT=8000
WEB_PORT=3000

QUIET=0
if [ "${1:-}" = "--quiet" ]; then
    QUIET=1
fi

if [ "$QUIET" -eq 0 ]; then
    echo "============================================================"
    echo "  QA Assistant - stopping services"
    echo "============================================================"
    echo
fi

# --- 1. recorded launcher PIDs --------------------------------------------
for name in api web; do
    pidfile="$RUN_DIR/$name.pid"
    [ -f "$pidfile" ] || continue

    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        # Kill the whole process group; uvicorn --reload spawns a child.
        kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
        sleep 0.5
        kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
        [ "$QUIET" -eq 0 ] && echo "  stopped $name process $pid"
    fi
    rm -f "$pidfile"
done

# --- 2. anything still listening on the project ports ---------------------
stop_port_listeners() {
    local port="$1"
    local pids=""
    if command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)"
    fi
    if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
        fuser -k "${port}/tcp" >/dev/null 2>&1 || true
        return 0
    fi

    for pid in $pids; do
        [ "$pid" = "$$" ] && continue
        kill -TERM "$pid" 2>/dev/null || true
        sleep 0.3
        kill -KILL "$pid" 2>/dev/null || true
        [ "$QUIET" -eq 0 ] && echo "  stopped listener on port $port (PID $pid)"
    done
}

for port in "$API_PORT" "$WEB_PORT"; do
    stop_port_listeners "$port"
done

if [ "$QUIET" -eq 0 ]; then
    echo
    echo "Done. Nothing should be listening on ports $API_PORT or $WEB_PORT."
    echo
fi

exit 0
