#!/usr/bin/env bash
# Tear down a background review session: kill the reviewer session + watcher +
# any docked viewport, and drop the index entry. Work dir (incl. RESULT) is kept by
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
  local sess viewport watcher_pid work be ref stranded=0
  sess="$(xr_session_name "$slug")"
  be="tmux"; ref="$sess"
  if [ -f "$f" ]; then
    viewport="$(jq -r '.viewport // empty' "$f")"
    watcher_pid="$(jq -r '.watcher_pid // empty' "$f")"
    work="$(jq -r '.work // empty' "$f")"
    be="$(jq -r '.backend // "tmux"' "$f")"
    ref="$(jq -r '.session_ref // .session' "$f")"
  fi
  # Close a docked viewport first, so killing the session doesn't orphan a pane.
  xr_be_close_viewport "${viewport:-}" "$be" || true
  if xr_be_usable "$be"; then
    xr_be_kill "$ref" "$be"
  else
    # Can't reach that backend from here, so we can't tell whether it is still
    # running — drop the index entry but say so instead of claiming it's dead.
    stranded=1
  fi
  [ -n "${watcher_pid:-}" ] && kill "$watcher_pid" 2>/dev/null || true
  rm -f "$f"
  if [ "$stranded" -eq 1 ]; then
    xr_log "session '$sess' ran under backend '$be', which is not reachable from here — the index entry is gone, but if the reviewer is still running you have to close it from a $be session."
  fi
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
