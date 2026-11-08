#!/usr/bin/env bash
# Smoke test of the clearance dashboard tab, in a real Hermes dashboard, with screenshots.
#
# Usage: tests/integration/dashboard_smoke.sh SCRATCH_DIR HERMES_SOURCE_DIR HERMES_PYTHON [SHOTS_DIR]
#   SCRATCH_DIR  a throwaway directory: the Hermes root, a demo project and the screenshots go under SCRATCH_DIR/dash13
#   SHOTS_DIR    where the screenshots go (default: SCRATCH_DIR/dash13/shots)
#   NODE_PATH    must reach a node_modules with playwright (chromium headless is used)
#
# What it does:
#   1. a throwaway Hermes root with the plugin installed in two profiles (default, ops), never ~/.hermes;
#   2. realistic evidence, driven through Hermes' own hooks and approval gate (tests/integration/dashboard_seed.py);
#   3. `hermes dashboard --isolated --port 9219 --host 127.0.0.1 --no-open`, with HERMES_GATEWAY_LOCK_DIR in the
#      scratch directory (never port 9119, never --stop);
#   4. scripts/dashboard_shots.cjs loads /clearance, asserts "Clearance", the map grid and "Models", and takes the
#      screenshots of every view at 1440x900 and 390x844, light and dark;
#   5. stops only the server it started (its own PID, checked against port 9219).
set -euo pipefail

SCRATCH="$1"; SRC="$2"; PY="$3"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BASE="$SCRATCH/dash13"
SHOTS="${4:-$BASE/shots}"
HERMES="$(dirname "$PY")/hermes"
PORT=9219
HH="$BASE/home"

case "$(cd "$SCRATCH" && pwd -P)" in "$HOME/.hermes"*) echo "refusing: scratch dir inside ~/.hermes" >&2; exit 1;; esac
[ -f "$ROOT/clearance/dashboard/dist/index.js" ] || { echo "FAIL: clearance/dashboard/dist/index.js is missing" >&2; exit 1; }
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "FAIL: port $PORT is already in use; not touching it" >&2; exit 1
fi

rm -rf "$BASE"
mkdir -p "$HH/plugins" "$HH/profiles/ops/plugins" "$BASE/locks" "$SHOTS"
for h in "$HH" "$HH/profiles/ops"; do
  rsync -a --exclude __pycache__ "$ROOT/clearance/" "$h/plugins/clearance/"
  printf 'plugins:\n  enabled: [clearance]\n' > "$h/config.yaml"
done

echo "== seeding evidence through the hooks"
env -u ANTHROPIC_API_KEY HERMES_HOME="$HH" HERMES_AGENT_DIR="$SRC" "$PY" "$ROOT/tests/integration/dashboard_seed.py" \
  main "$BASE/shop" 2>"$BASE/seed-main.log"
env -u ANTHROPIC_API_KEY HERMES_HOME="$HH/profiles/ops" HERMES_AGENT_DIR="$SRC" "$PY" \
  "$ROOT/tests/integration/dashboard_seed.py" ops "$BASE/ops-project" 2>"$BASE/seed-ops.log"

echo "== starting the dashboard on 127.0.0.1:$PORT"
env -u ANTHROPIC_API_KEY HERMES_HOME="$HH" HERMES_GATEWAY_LOCK_DIR="$BASE/locks" \
  "$HERMES" dashboard --isolated --port $PORT --host 127.0.0.1 --no-open >"$BASE/dashboard.log" 2>&1 &
PID=$!
disown "$PID" 2>/dev/null || true

stop() {
  # Only our server: its PID and its children, and only if what listens on the port is one of them.
  local pids="$PID $(pgrep -P "$PID" 2>/dev/null | tr '\n' ' ')"
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 50); do kill -0 "$PID" 2>/dev/null || break; sleep 0.1; done
  kill -9 $pids 2>/dev/null || true
  local left; left="$(lsof -nP -t -iTCP:$PORT -sTCP:LISTEN 2>/dev/null || true)"
  for p in $left; do
    case " $pids " in *" $p "*) kill -9 "$p" 2>/dev/null || true;; esac
  done
}
trap stop EXIT

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:$PORT/clearance" >/dev/null 2>&1; then break; fi
  kill -0 "$PID" 2>/dev/null || { echo "FAIL: the dashboard exited"; tail -40 "$BASE/dashboard.log"; exit 1; }
  sleep 0.5
done
listener="$(lsof -nP -t -iTCP:$PORT -sTCP:LISTEN 2>/dev/null | head -1 || true)"
case " $PID $(pgrep -P "$PID" | tr '\n' ' ') " in *" $listener "*) ;; *)
  echo "FAIL: port $PORT is held by $listener, not by our server $PID" >&2; exit 1;; esac

echo "== screenshots"
node "$ROOT/scripts/dashboard_shots.cjs" "http://127.0.0.1:$PORT" "$SHOTS"
echo "OK: dashboard smoke test passed; screenshots in $SHOTS"
