#!/usr/bin/env bash
# Cosmetic-only: renders a small, periodically-refreshing status card above an
# agent's pane, loosely styled after a "mission control" swarm dashboard.
# Reads SWARM_STATUS.md for this role's current task; pure display, no
# side effects. Started by scripts/swarm/start.sh.

set -euo pipefail

ROLE="${1:?usage: status-card.sh <role>}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATUS_FILE="$PROJECT_DIR/SWARM_STATUS.md"
WIDTH=34
INNER=$((WIDTH-4))  # minus the "│ " / " │" borders

case "$ROLE" in
  researcher) COLOR=$'\033[1;33m' ;;  # yellow
  builder)    COLOR=$'\033[1;34m' ;;  # blue
  reviewer)   COLOR=$'\033[1;35m' ;;  # magenta
  *)          COLOR=$'\033[1;37m' ;;
esac
RESET=$'\033[0m'

border() { printf '%s%s%s\n' "$COLOR" "$1$(printf -- '─%.0s' $(seq 1 $((WIDTH-2))))$2" "$RESET"; }
line() {
  local text="$1"
  [ ${#text} -gt $INNER ] && text="${text:0:$((INNER-1))}…"
  printf '%s│%s %-*s %s│%s\n' "$COLOR" "$RESET" "$INNER" "$text" "$COLOR" "$RESET"
}

while true; do
  clear
  TASK="—"
  STATUS="idle"
  if [ -f "$STATUS_FILE" ]; then
    MATCH=$(awk -F'|' -v r="$ROLE" '
      NF>3 {
        owner=$3; gsub(/^[ \t]+|[ \t]+$/, "", owner)
        if (owner==r || owner=="tap-" r) { task=$2; status=$4; gsub(/^[ \t]+|[ \t]+$/, "", task); gsub(/^[ \t]+|[ \t]+$/, "", status); print task "\t" status }
      }' "$STATUS_FILE" | tail -1)
    if [ -n "$MATCH" ]; then
      TASK="${MATCH%%$'\t'*}"
      STATUS="${MATCH##*$'\t'}"
    fi
  fi

  case "$STATUS" in
    in-progress) STATUS_TXT="working" ;;
    review)      STATUS_TXT="awaiting review" ;;
    done)        STATUS_TXT="done" ;;
    blocked)     STATUS_TXT="blocked" ;;
    *)           STATUS_TXT="idle" ;;
  esac

  border "┌" "┐"
  line "● $(echo "$ROLE" | tr '[:lower:]' '[:upper:]')"
  line "$TASK"
  line "$STATUS_TXT"
  border "└" "┘"

  sleep 4
done
