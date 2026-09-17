#!/usr/bin/env bash
# Show all known background review sessions and their state.
#
# Usage: status.sh [slug]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

xr_need jq
xr_init_home

want="${1:-}"
want="${want#"$XRLIVE_SESSION_PREFIX"}"

found=0
for f in "$XRLIVE_SESSIONS"/*.json; do
  [ -e "$f" ] || continue
  slug="$(basename "$f" .json)"
  [ -z "$want" ] || [ "$want" = "$slug" ] || continue
  found=1

  sess="$(jq -r '.session' "$f")"
  be="$(jq -r '.backend // "tmux"' "$f")"
  ref="$(jq -r '.session_ref // .session' "$f")"
  reviewer="$(jq -r '.reviewer' "$f")"
  repo_key="$(jq -r '.repo_key' "$f")"
  branch="$(jq -r '.branch' "$f")"
  scope="$(jq -r '.scope' "$f")"
  result="$(jq -r '.result' "$f")"
  created="$(jq -r '.created' "$f")"
  work="$(jq -r '.work // empty' "$f")"
  watch="$(xr_get_watch_state "$work" 2>/dev/null || true)"
  watch_detail=""
  [ -n "$work" ] && [ -f "$work/WATCH_STATE" ] && watch_detail="$(sed -n '2p' "$work/WATCH_STATE" 2>/dev/null || true)"

  if [ -s "$result" ]; then
    state="done (result ready)"
  elif xr_be_ended "$work" "$ref" "$be"; then
    state="ended (no result)"
  elif ! xr_be_usable "$be"; then
    # Started under the other backend (e.g. a tmux review, listed from Orca).
    # The durable watch state is all we can honestly report.
    state="unknown — backend '$be' not reachable from here (last known: ${watch:-?})"
  elif xr_be_alive "$ref" "$be"; then
    if [ "$watch" = "stuck" ]; then
      state="stuck (trust/권한 프롬프트 — /xreview:live peek 로 응답)"
    else
      state="running"
    fi
  else
    state="gone"
  fi

  printf '● %s\n' "$slug"
  printf '    state    : %s\n' "$state"
  [ "$watch" = "stuck" ] && [ -n "$watch_detail" ] && printf '    ⚠ detail : %s\n' "$watch_detail"
  printf '    reviewer : %s    scope: %s\n' "$reviewer" "$scope"
  printf '    repo     : %s  (branch %s)\n' "$repo_key" "$branch"
  printf '    session  : %s (%s)    started: %s\n' "$sess" "$be" "$created"
  [ -s "$result" ] && printf '    result   : %s\n' "$result"
  printf '\n'
done

if [ "$found" -eq 0 ]; then
  if [ -n "$want" ]; then
    echo "no review session for slug '$want'."
  else
    echo "no review sessions. Start one with /xreview:live."
  fi
fi
