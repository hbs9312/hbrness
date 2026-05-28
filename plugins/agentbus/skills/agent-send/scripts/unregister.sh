#!/usr/bin/env bash
# /agent-unregister [alias]
# If alias omitted, removes whichever entry points to the current pane.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

ab_need_jq
ab_init_home

if [ $# -gt 0 ] && [ -n "$1" ]; then
  alias="$1"
  exists="$(jq -r --arg a "$alias" '.[$a] // empty' "$REGISTRY")"
  if [ -z "$exists" ] || [ "$exists" = "null" ]; then
    ab_log "no such alias: $alias"
    exit 0
  fi
  ab_registry_remove_alias "$alias"
  echo "unregistered: $alias"
else
  rc=0
  pane="$(ab_current_pane)" || rc=$?
  case $rc in
    0) : ;;
    1) ab_die "not inside tmux and no alias given" ;;
    2) ab_die "$(ab_tmux_access_message)" ;;
  esac
  before="$(jq -r --arg p "$pane" '[ to_entries[] | select(.value.pane == $p) | .key ] | join(",")' "$REGISTRY")"
  if [ -z "$before" ]; then
    echo "no entry registered for current pane ($pane)"
    exit 0
  fi
  ab_registry_remove_by_pane "$pane"
  echo "unregistered (pane $pane): $before"
fi
