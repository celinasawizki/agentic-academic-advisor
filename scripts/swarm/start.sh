#!/usr/bin/env bash
# Launch (or reattach to) the four-agent Claude Code swarm for this repo:
# orchestrator / researcher / builder / reviewer, each a real `claude`
# session in its own tmux pane, coordinating over SendMessage/ListAgents.
# Adapted from github.com/celinasawizki/vscode-swarm-setup.
#
# Usage:
#   ./scripts/swarm/start.sh                       # default permissions
#   SWARM_PERMISSION_MODE=acceptEdits ./scripts/swarm/start.sh
#   SWARM_DETACH=1 ./scripts/swarm/start.sh        # start without attaching
#   ./scripts/swarm/stop.sh                        # end all four sessions
#
# Runs on its own tmux socket (-L tap-agents), separate from dev-swarm.sh
# (-L tap-swarm) and your default tmux server. Re-running attaches.

set -euo pipefail

SESSION="tap-agents"
SOCKET="tap-agents"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SWARM_DIR="$PROJECT_DIR/scripts/swarm"
TMUX_CONF="$SWARM_DIR/tmux.conf"

tmuxs() { tmux -L "$SOCKET" "$@"; }

command -v tmux >/dev/null 2>&1 || { echo "tmux is not installed: brew install tmux" >&2; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "Claude Code CLI ('claude') is not on PATH." >&2; exit 1; }

attach() {
  if [ -n "${SWARM_DETACH:-}" ] || [ ! -t 1 ]; then
    echo "Swarm running detached. Attach with: tmux -L $SOCKET attach -t $SESSION"
  elif [ -n "${TMUX:-}" ]; then
    tmuxs switch-client -t "$SESSION"
  else
    tmuxs attach -t "$SESSION"
  fi
}

if tmuxs has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running."
  attach
  exit 0
fi

[ -f "$PROJECT_DIR/SWARM_STATUS.md" ] || cp "$SWARM_DIR/SWARM_STATUS.template.md" "$PROJECT_DIR/SWARM_STATUS.md"

PERM_FLAG=""
if [ -n "${SWARM_PERMISSION_MODE:-}" ]; then
  PERM_FLAG="--permission-mode $SWARM_PERMISSION_MODE"
fi

launch_agent() {
  local pane_id="$1" role="$2" seed="$3"
  tmuxs select-pane -t "$pane_id" -T "$role"
  tmuxs send-keys -t "$pane_id" \
    "clear; claude --name tap-$role --append-system-prompt-file scripts/swarm/roles/$role.md $PERM_FLAG \"$seed\"" \
    Enter
}

add_status_card() {
  local main_pane="$1" role="$2" card_pane
  card_pane=$(tmuxs split-window -v -b -l 6 -t "$main_pane" -c "$PROJECT_DIR" -P -F '#{pane_id}')
  tmuxs send-keys -t "$card_pane" "clear; ./scripts/swarm/status-card.sh $role" Enter
}

echo "Creating tmux session '$SESSION' on socket '$SOCKET'..."
tmux -L "$SOCKET" -f "$TMUX_CONF" new-session -d -s "$SESSION" -c "$PROJECT_DIR" -x 220 -y 58

PANE_TL=$(tmuxs list-panes -t "$SESSION" -F '#{pane_id}' | head -1)
PANE_TR=$(tmuxs split-window -h -l 50% -t "$PANE_TL" -c "$PROJECT_DIR" -P -F '#{pane_id}')
PANE_BL=$(tmuxs split-window -v -l 50% -t "$PANE_TL" -c "$PROJECT_DIR" -P -F '#{pane_id}')
PANE_BR=$(tmuxs split-window -v -l 50% -t "$PANE_TR" -c "$PROJECT_DIR" -P -F '#{pane_id}')

add_status_card "$PANE_TR" researcher
add_status_card "$PANE_BL" builder
add_status_card "$PANE_BR" reviewer

COMMON="Read CLAUDE.md and scripts/swarm/PROTOCOL.md in this repo"
launch_agent "$PANE_TL" orchestrator "You are online as tap-orchestrator. $COMMON, then SWARM_STATUS.md. Introduce yourself in one short line and wait for a task (from the human in this pane or via SendMessage)."
launch_agent "$PANE_TR" researcher "You are online as tap-researcher. $COMMON. Introduce yourself in one short line, then wait for a task from tap-orchestrator via SendMessage."
launch_agent "$PANE_BL" builder "You are online as tap-builder. $COMMON. Introduce yourself in one short line, then wait for a task from tap-orchestrator via SendMessage."
launch_agent "$PANE_BR" reviewer "You are online as tap-reviewer. $COMMON. Introduce yourself in one short line, then wait for a review request via SendMessage."

tmuxs select-pane -t "$PANE_TL"
attach
