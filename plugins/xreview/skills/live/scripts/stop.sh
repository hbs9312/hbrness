#!/usr/bin/env bash
# Tear down a background review session: kill the tmux session + watcher + any
# docked viewport, and drop the index entry. Work dir (incl. RESULT) is kept by
# default so you can still read the review; pass --purge to remove it too.
#
# Usage:
#   stop.sh [slug] [--purge]
#   stop.sh --all [--purge]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

xr_need jq
xr_need tmux
xr_init_home

slug=""
all=0
purge=0
while [ $# -gt 0 ]; do
  case "$1" in
    --all)   all=1; shift ;;
    --purge) purge=1; shift ;;
    -*) xr_die "unknown flag: $1" ;;
    *)  slug="$1"; shift ;;
  esac
done

_stop_one() {
  local slug="$1" f="$XRLIVE_SESSIONS/$1.json"
  local sess viewport watcher_pid work
  sess="$(xr_session_name "$slug")"
  if [ -f "$f" ]; then
    viewport="$(jq -r '.viewport // empty' "$f")"
    watcher_pid="$(jq -r '.watcher_pid // empty' "$f")"
    work="$(jq -r '.work // empty' "$f")"
  fi
  # Close docked viewport first (so killing the session doesn't orphan a pane).
  if [ -n "${viewport:-}" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$viewport"; then
    tmux kill-pane -t "$viewport" 2>/dev/null || true
  fi
  tmux kill-session -t "=$sess" 2>/dev/null || true
  [ -n "${watcher_pid:-}" ] && kill "$watcher_pid" 2>/dev/null || true
  rm -f "$f"
  if [ "$purge" -eq 1 ] && [ -n "${work:-}" ] && [ -d "$work" ]; then
    case "$work" in
      "$XRLIVE_HOME"/*) rm -rf "$work" ;;   # safety: only under our home
    esac
    printf 'stopped %s (purged work dir)\n' "$slug"
  else
    printf 'stopped %s%s\n' "$slug" "$([ -n "${work:-}" ] && printf ' (kept: %s)' "$work")"
  fi
}

if [ "$all" -eq 1 ]; then
  any=0
  for f in "$XRLIVE_SESSIONS"/*.json; do
    [ -e "$f" ] || continue
    any=1
    _stop_one "$(basename "$f" .json)"
  done
  [ "$any" -eq 1 ] || echo "no review sessions to stop."
  exit 0
fi

slug="$(xr_resolve_slug "$slug")"
_stop_one "$slug"
