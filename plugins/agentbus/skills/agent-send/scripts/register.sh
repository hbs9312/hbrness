#!/usr/bin/env bash
# /agent-register <alias> [--tool claude|codex|shell] [--pane <%paneId>]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

alias=""
tool=""
pane_override=""

while [ $# -gt 0 ]; do
  case "$1" in
    --tool)  tool="$2"; shift 2 ;;
    --pane)  pane_override="$2"; shift 2 ;;
    --help|-h)
      cat <<EOF
Usage: agent-register <alias> [--tool claude|codex|shell] [--pane <%paneId>]

Registers the current tmux pane (or the one given via --pane) under <alias>
into the agentbus registry. If --tool is omitted, auto-detect (CODEX_* env
implies codex, otherwise claude).
EOF
      exit 0
      ;;
    -*)      ab_die "unknown flag: $1" ;;
    *)
      if [ -z "$alias" ]; then alias="$1"; else ab_die "extra arg: $1"; fi
      shift
      ;;
  esac
done

[ -n "$alias" ] || ab_die "alias is required. usage: agent-register <alias> [--tool ...]"
[[ "$alias" =~ ^[A-Za-z0-9_-]+$ ]] || ab_die "alias must be [A-Za-z0-9_-]+ (got: $alias)"

ab_need_jq
ab_need_tmux
ab_init_home

# Resolve pane. Note: `func; case $?` would let `set -e` kill us before we
# reach the case, so capture the rc through `|| rc=$?`.
if [ -n "$pane_override" ]; then
  pane="$pane_override"
else
  rc=0
  pane="$(ab_current_pane)" || rc=$?
  case $rc in
    0) : ;;
    1) ab_die "not inside tmux — set TMUX or pass --pane" ;;
    2) ab_die "$(ab_tmux_access_message)" ;;
  esac
fi

# Verify pane status with the three-state probe.
#   0 = exists, 1 = truly missing, 2 = cannot query (sandbox/permission/no-server).
# Critically, do NOT report "pane does not exist" on access failures.
rc=0
ab_pane_status "$pane" || rc=$?
case $rc in
  0) : ;;
  1) ab_die "pane $pane does not exist" ;;
  2) ab_die "$(ab_tmux_access_message)" ;;
esac

if ! info="$(ab_pane_info "$pane")"; then
  ab_die_tmux_or "cannot read info for pane $pane"
fi
session="$(printf '%s' "$info" | awk -F'|' '{print $1}')"
window="$(printf '%s' "$info" | awk -F'|' '{print $2}')"
cmd="$(printf '%s'    "$info" | awk -F'|' '{print $4}')"
pid="$(printf '%s'    "$info" | awk -F'|' '{print $5}')"

if [ -z "$tool" ]; then
  if ab_is_codex_session; then
    tool="codex"
  elif [ "$cmd" = "claude" ] || [ "$cmd" = "node" ]; then
    tool="claude"
  elif [[ "$cmd" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    # Recent claude CLI surfaces as its version string in pane_current_command.
    tool="claude"
  else
    tool="$cmd"
  fi
fi

# Refuse to overwrite a different live pane silently.
# If we cannot determine the prior pane's liveness (access denied), be
# conservative: treat it as live (refuse the overwrite) rather than wiping
# someone else's registration based on a sandbox failure.
existing="$(jq -r --arg a "$alias" '.[$a] // empty | tojson' "$REGISTRY")"
if [ -n "$existing" ] && [ "$existing" != "null" ]; then
  existing_pane="$(printf '%s' "$existing" | jq -r '.pane')"
  if [ "$existing_pane" != "$pane" ]; then
    rc=0
    ab_pane_status "$existing_pane" || rc=$?
    case $rc in
      0) ab_die "alias '$alias' already points to active pane $existing_pane. Unregister first or pick another name." ;;
      1) : ;;  # prior pane is gone — safe to overwrite
      2) ab_die "alias '$alias' already points to pane $existing_pane and tmux liveness check failed: $(ab_tmux_access_message) Refusing to overwrite. Re-run with tmux access, or unregister explicitly." ;;
    esac
  fi
fi

# Also drop any prior entry for this pane (one pane = one alias)
ab_registry_remove_by_pane "$pane" >/dev/null 2>&1 || true

ab_registry_put "$alias" "$session" "$window" "$pane" "$tool" "$pid"

cat <<EOF
registered: $alias
  session:  $session
  window:   $window
  pane:     $pane
  tool:     $tool
  pid:      $pid
registry: $REGISTRY
EOF
