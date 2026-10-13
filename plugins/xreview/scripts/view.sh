#!/usr/bin/env bash
# View controls for a background review session. Non-destructive — showing the
# reviewer never kills it.
#
# A tmux reviewer session (the default, under tmux and Orca alike) is shown in a
# split on the right of this pane or terminal that attaches to it; peek and dock
# both open it, and undock closes it. Closing the split only detaches.
# A reviewer in an Orca tab (where tmux is missing) is its own view: peek and
# dock switch to that tab and undock switches back.
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
  local v="$1" vbe="${2:-}" tmp
  tmp="$(mktemp)"
  jq --arg v "$v" --arg b "$vbe" '.viewport=$v | .viewport_backend=$b' "$meta" > "$tmp" && mv "$tmp" "$meta"
}

case "$action" in
  peek|dock)
    xr_be_alive "$ref" "$be" || xr_die "session $sess is not running (see /xreview:status)"
    case "$be" in
      tmux)
        existing="$(xr_meta "$slug" viewport || true)"
        if xr_be_viewport_alive "${existing:-}" "$(xr_slug_viewport_backend "$slug")"; then
          printf '%s is already open in a split on the right (close it with /xreview:live undock)\n' "$slug"
          exit 0
        fi
        viewer="$(xr_backend)"
        viewport="$(xr_be_open_viewport "$ref" "$viewer" "$(xr_launcher_id)")" \
          || xr_die "could not open a split for $slug"
        set_viewport "$viewport" "$viewer"
        printf 'opened %s in a split on the right (reviewer still running in background; close it with /xreview:live undock)\n' "$slug"
        ;;
      orca)
        # The reviewer's tab is the view. Remember where we came from so undock
        # can switch back.
        set_viewport "${ORCA_TERMINAL_HANDLE:-}"
        orca terminal switch --terminal "$ref" --json >/dev/null 2>&1 \
          || xr_die "could not switch to the reviewer tab for $slug"
        printf 'switched to the reviewer tab for %s — it runs in an Orca tab because tmux is not installed, so there is no split to open. Back with /xreview:live undock.\n' "$slug"
        ;;
    esac
    ;;
  undock)
    viewport="$(xr_meta "$slug" viewport || true)"
    case "$be" in
      tmux)
        if xr_be_close_viewport "${viewport:-}" "$(xr_slug_viewport_backend "$slug")"; then
          set_viewport ""
          printf 'closed the split for %s (reviewer still running in background)\n' "$slug"
        else
          printf 'no split open for %s\n' "$slug"
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
