#!/usr/bin/env bash
# Stop the tap-agents tmux session (on its dedicated 'tap-agents' socket).
# The underlying claude sessions exit with their panes; nothing is left
# running in the background. Re-run ./scripts/start-swarm.sh to restart.

set -euo pipefail

SESSION="tap-agents"
SOCKET="tap-agents"

if tmux -L "$SOCKET" has-session -t "$SESSION" 2>/dev/null; then
  tmux -L "$SOCKET" kill-session -t "$SESSION"
  echo "Stopped '$SESSION'."
else
  echo "'$SESSION' is not running."
fi
