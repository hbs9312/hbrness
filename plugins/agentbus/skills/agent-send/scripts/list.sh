#!/usr/bin/env bash
# /agent-list — show registered agents, prune stale ones first
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

ab_need_jq
ab_need_tmux
ab_init_home

pruned="$(ab_registry_prune_stale)"
if [ -n "$pruned" ]; then
  echo "pruned stale entries:"
  printf '  - %s\n' $pruned
  echo
fi

if [ ! -s "$REGISTRY" ] || [ "$(jq -r 'length' "$REGISTRY")" = "0" ]; then
  echo "no agents registered. use /agent-register <alias> in each session."
  exit 0
fi

self_pane="$(ab_current_pane 2>/dev/null || true)"

printf '%-16s  %-22s  %-8s  %-8s  %-7s  %s\n' \
  "ALIAS" "SESSION:WINDOW" "PANE" "TOOL" "SELF?" "REGISTERED"

ab_registry_list | while IFS=$'\t' read -r alias sw pane tool pid_part ts_part; do
  ts="${ts_part#registered=}"
  flag=""
  if [ -n "$self_pane" ] && [ "$self_pane" = "$pane" ]; then flag="*"; fi
  printf '%-16s  %-22s  %-8s  %-8s  %-7s  %s\n' \
    "$alias" "$sw" "$pane" "$tool" "$flag" "$ts"
done
