#!/usr/bin/env bash
# Launch (or reattach to) the planner's dev session in tmux: three panes showing
# what is actually running.
#
#   ┌──────────────────────────────────────────────┐
#   │ agents: live orchestration feed (every agent  │
#   │ start/finish, research log lines, sources)    │
#   ├───────────────────────┬──────────────────────┤
#   │ api: FastAPI (uvicorn)│ web: Next.js dev      │
#   └───────────────────────┴──────────────────────┘
#
# Usage:  ./scripts/dev-swarm.sh            (API_PORT=8010 WEB_PORT=3000 by default)
#         ./scripts/dev-swarm.sh stop       (kill the session)
#
# Runs on its own tmux socket (-L tap-swarm), so it never touches your default
# tmux server. Safe to re-run: an existing session is attached, not duplicated.

set -euo pipefail

SESSION="tap"
SOCKET="tap-swarm"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${API_PORT:-8010}"
WEB_PORT="${WEB_PORT:-3000}"
PY="$ROOT/apps/api/.venv/bin"

tmuxs() { tmux -L "$SOCKET" "$@"; }

command -v tmux >/dev/null 2>&1 || { echo "tmux is not installed: brew install tmux" >&2; exit 1; }
[ -x "$PY/uvicorn" ] || { echo "API virtualenv missing: cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }

if [ "${1:-}" = "stop" ]; then
  tmuxs kill-session -t "$SESSION" 2>/dev/null && echo "Stopped session '$SESSION'." || echo "No session running."
  exit 0
fi

attach() {
  if [ -n "${TMUX:-}" ]; then tmuxs switch-client -t "$SESSION"; else tmuxs attach -t "$SESSION"; fi
}

if tmuxs has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running — attaching."
  attach
  exit 0
fi

tmuxs new-session -d -s "$SESSION" -n planner -x 220 -y 60 -c "$ROOT/apps/api"
tmuxs set -t "$SESSION" pane-border-status top
tmuxs set -t "$SESSION" pane-border-format " #{pane_index}: #{pane_title} "
tmuxs set -t "$SESSION" mouse on

AGENTS=$(tmuxs display -p -t "$SESSION:planner" '#{pane_id}')
API=$(tmuxs split-window -v -p 40 -t "$AGENTS" -c "$ROOT/apps/api" -P -F '#{pane_id}')
WEB=$(tmuxs split-window -h -p 50 -t "$API" -c "$ROOT/apps/web" -P -F '#{pane_id}')

tmuxs select-pane -t "$AGENTS" -T "agents · orchestration feed"
tmuxs select-pane -t "$API" -T "api · FastAPI on :$API_PORT"
tmuxs select-pane -t "$WEB" -T "web · Next.js on :$WEB_PORT"

tmuxs send-keys -t "$API" "clear; $PY/uvicorn app.main:app --host 127.0.0.1 --port $API_PORT --reload --reload-dir app" Enter
tmuxs send-keys -t "$WEB" "clear; NEXT_PUBLIC_API_URL=http://127.0.0.1:$API_PORT npx next dev --port $WEB_PORT" Enter
tmuxs send-keys -t "$AGENTS" "clear; sleep 4; $PY/python -m scripts.watch_agents" Enter
tmuxs select-pane -t "$AGENTS"

echo "Started '$SESSION': agents feed, API on :$API_PORT, web on http://localhost:$WEB_PORT"
[ -t 1 ] && attach || echo "Attach with: tmux -L $SOCKET attach -t $SESSION"
