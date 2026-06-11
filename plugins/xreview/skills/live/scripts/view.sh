#!/usr/bin/env bash
# View controls for a background review session. Non-destructive: peek/dock open
# a nested `tmux attach` viewport onto the detached reviewer session; closing the
# viewport never kills the reviewer. undock closes the docked split.
#
# Usage:
#   view.sh peek   [slug]      # open the reviewer in a tmux popup
#   view.sh dock   [slug]      # open the reviewer as a split pane in this window
#   view.sh undock [slug]      # close the docked split pane
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

action="${1:-}"; shift || true
slug="${1:-}"

xr_need tmux
xr_in_tmux || xr_die "not inside a tmux session"
xr_init_home

slug="$(xr_resolve_slug "$slug")"
sess="$(xr_session_name "$slug")"
meta="$XRLIVE_SESSIONS/$slug.json"
[ -f "$meta" ] || xr_die "no session metadata for slug '$slug'"

case "$action" in
  peek)
    xr_session_exists "$sess" || xr_die "session $sess is not running (see /xreview:live status)"
    # env -u TMUX → attach as a fresh client (avoids tmux's nested-session refusal).
    tmux display-popup -w 90% -h 90% -E "env -u TMUX tmux attach-session -t $(xr_shq "=$sess")"
    printf 'closed popup for %s (reviewer still running in background)\n' "$slug"
    ;;
  dock)
    xr_session_exists "$sess" || xr_die "session $sess is not running (see /xreview:live status)"
    local_pane="$(xr_current_pane)"
    # If a viewport already exists and is alive, just select it.
    existing="$(xr_meta "$slug" viewport || true)"
    if [ -n "${existing:-}" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$existing"; then
      tmux select-pane -t "$existing"
      printf 'already docked for %s (pane %s)\n' "$slug" "$existing"
      exit 0
    fi
    viewport="$(tmux split-window -h -P -F '#{pane_id}' -t "$local_pane" \
      "env -u TMUX tmux attach-session -t $(xr_shq "=$sess")")"
    tmp="$(mktemp)"; jq --arg v "$viewport" '.viewport=$v' "$meta" > "$tmp" && mv "$tmp" "$meta"
    printf 'docked %s as pane %s (undock with /xreview:live undock)\n' "$slug" "$viewport"
    ;;
  undock)
    viewport="$(xr_meta "$slug" viewport || true)"
    if [ -n "${viewport:-}" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$viewport"; then
      tmux kill-pane -t "$viewport"
      tmp="$(mktemp)"; jq '.viewport=""' "$meta" > "$tmp" && mv "$tmp" "$meta"
      printf 'undocked %s (reviewer still running in background)\n' "$slug"
    else
      printf 'no docked viewport for %s\n' "$slug"
    fi
    ;;
  *)
    xr_die "usage: view.sh {peek|dock|undock} [slug]"
    ;;
esac
