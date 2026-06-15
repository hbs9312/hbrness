#!/usr/bin/env bash
# Show all known background review sessions and their state.
#
# Usage: status.sh [slug]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

xr_need jq
xr_need tmux
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
  reviewer="$(jq -r '.reviewer' "$f")"
  repo_key="$(jq -r '.repo_key' "$f")"
  branch="$(jq -r '.branch' "$f")"
  scope="$(jq -r '.scope' "$f")"
  result="$(jq -r '.result' "$f")"
  created="$(jq -r '.created' "$f")"

  if [ -s "$result" ]; then
    state="done (result ready)"
  elif xr_session_exists "$sess"; then
    if [ "$(xr_session_pane_dead "$sess")" = "1" ]; then
      state="ended (no result)"
    else
      state="running"
    fi
  else
    state="gone"
  fi

  printf '● %s\n' "$slug"
  printf '    state    : %s\n' "$state"
  printf '    reviewer : %s    scope: %s\n' "$reviewer" "$scope"
  printf '    repo     : %s  (branch %s)\n' "$repo_key" "$branch"
  printf '    session  : %s    started: %s\n' "$sess" "$created"
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
