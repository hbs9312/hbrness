#!/usr/bin/env bash
# View controls for a background review session. Non-destructive — showing the
# reviewer never kills it.
#
# tmux: peek opens a popup and dock opens a split pane, both nested
#   `tmux attach` viewports onto the detached session; undock closes the split.
# orca: the reviewer already lives in its own terminal tab, so peek and dock
#   both switch to it and undock switches back to the launcher tab.
#
# Usage:
#   view.sh peek   [slug]
#   view.sh dock   [slug]
#   view.sh undock [slug]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

action="${1:-}"; shift || true
slug="${1:-}"

xr_need jq
xr_backend_require
xr_init_home

slug="$(xr_resolve_slug "$slug")"
sess="$(xr_session_name "$slug")"
meta="$XRLIVE_SESSIONS/$slug.json"
[ -f "$meta" ] || xr_die "no session metadata for slug '$slug'"

be="$(xr_slug_backend "$slug")"
ref="$(xr_slug_ref "$slug")"
xr_be_usable "$be" || xr_die "session '$slug' runs on backend '$be', which is not reachable from here. Open it from a $be session, or read the result file directly (/xreview:status)."

set_viewport() {
  local v="$1" tmp
  tmp="$(mktemp)"; jq --arg v "$v" '.viewport=$v' "$meta" > "$tmp" && mv "$tmp" "$meta"
}

case "$action" in
  peek)
    xr_be_alive "$ref" "$be" || xr_die "session $sess is not running (see /xreview:status)"
    case "$be" in
      tmux)
        # env -u TMUX → attach as a fresh client (avoids tmux's nested-session refusal).
        tmux display-popup -w 90% -h 90% -E "env -u TMUX tmux attach-session -t $(xr_shq "=$sess")"
        printf 'closed popup for %s (reviewer still running in background)\n' "$slug"
        ;;
      orca)
        orca terminal switch --terminal "$ref" --json >/dev/null 2>&1 \
          || xr_die "could not switch to the reviewer tab for $slug"
        printf 'switched to the reviewer tab for %s (come back with /xreview:live undock)\n' "$slug"
        ;;
    esac
    ;;
  dock)
    xr_be_alive "$ref" "$be" || xr_die "session $sess is not running (see /xreview:status)"
    case "$be" in
      tmux)
        local_pane="$(xr_launcher_id)"
        # If a viewport already exists and is alive, just select it.
        existing="$(xr_meta "$slug" viewport || true)"
        if [ -n "${existing:-}" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$existing"; then
          tmux select-pane -t "$existing"
          printf 'already docked for %s (pane %s)\n' "$slug" "$existing"
          exit 0
        fi
        viewport="$(tmux split-window -h -P -F '#{pane_id}' -t "$local_pane" \
          "env -u TMUX tmux attach-session -t $(xr_shq "=$sess")")"
        set_viewport "$viewport"
        printf 'docked %s as pane %s (undock with /xreview:live undock)\n' "$slug" "$viewport"
        ;;
      orca)
        # Orca has no second view onto one terminal — the reviewer tab is the
        # view. Remember where we came from so undock can switch back.
        set_viewport "${ORCA_TERMINAL_HANDLE:-}"
        orca terminal switch --terminal "$ref" --json >/dev/null 2>&1 \
          || xr_die "could not switch to the reviewer tab for $slug"
        printf 'switched to the reviewer tab for %s — Orca shows it as its own tab rather than a split, so dock and peek do the same thing here. Back with /xreview:live undock.\n' "$slug"
        ;;
    esac
    ;;
  undock)
    viewport="$(xr_meta "$slug" viewport || true)"
    case "$be" in
      tmux)
        if xr_be_close_viewport "${viewport:-}" tmux; then
          set_viewport ""
          printf 'undocked %s (reviewer still running in background)\n' "$slug"
        else
          printf 'no docked viewport for %s\n' "$slug"
        fi
        ;;
      orca)
        back="${viewport:-${ORCA_TERMINAL_HANDLE:-}}"
        if [ -n "$back" ] && orca terminal switch --terminal "$back" --json >/dev/null 2>&1; then
          set_viewport ""
          printf 'switched back from %s (reviewer still running in its tab)\n' "$slug"
        else
          printf 'nowhere to switch back to for %s — pick a tab yourself\n' "$slug"
        fi
        ;;
    esac
    ;;
  *)
    xr_die "usage: view.sh {peek|dock|undock} [slug]"
    ;;
esac
