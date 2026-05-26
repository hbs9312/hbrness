#!/usr/bin/env bash
# /agent-inbox [--alias <name>] [list|show <id>|mark <id>|clear]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

alias=""
sub="list"
arg=""

while [ $# -gt 0 ]; do
  case "$1" in
    --alias) alias="$2"; shift 2 ;;
    list|show|mark|clear)
      sub="$1"
      shift
      if [ "$sub" = "show" ] || [ "$sub" = "mark" ]; then
        arg="${1:-}"
        [ -n "$arg" ] && shift || true
      fi
      ;;
    --help|-h)
      cat <<EOF
Usage: agent-inbox [--alias <name>] [list | show <id> | mark <id> | clear]

list           show all mailbox messages for the inbox (default)
show <id>      print the message JSON
mark <id>      mark message as read (creates a sibling .read marker)
clear          delete all messages in the inbox (asks confirmation)

If --alias is omitted, the inbox of the alias mapped to the current pane is used.
EOF
      exit 0
      ;;
    *) ab_die "unknown arg: $1" ;;
  esac
done

ab_need_jq
ab_init_home

if [ -z "$alias" ]; then
  self_pane="$(ab_current_pane 2>/dev/null || true)"
  if [ -n "$self_pane" ]; then
    alias="$(jq -r --arg p "$self_pane" '[ to_entries[] | select(.value.pane == $p) | .key ] | first // empty' "$REGISTRY" 2>/dev/null || true)"
  fi
fi
[ -n "$alias" ] || ab_die "no alias detected for current pane and --alias not given"

dir="$INBOX_ROOT/$alias"
mkdir -p "$dir"

case "$sub" in
  list)
    if ! ls "$dir"/*.json >/dev/null 2>&1; then
      echo "inbox '$alias' is empty."
      exit 0
    fi
    echo "inbox: $alias  ($dir)"
    for f in "$dir"/*.json; do
      base="$(basename "$f" .json)"
      id="$(jq -r '.id' "$f" 2>/dev/null || echo '?')"
      from="$(jq -r '.from' "$f" 2>/dev/null || echo '?')"
      kind="$(jq -r '.kind' "$f" 2>/dev/null || echo '?')"
      sent="$(jq -r '.sent_at' "$f" 2>/dev/null || echo '?')"
      preview="$(jq -r '.body' "$f" 2>/dev/null | tr -d '\n' | cut -c1-60)"
      read_mark=" "
      [ -f "$f.read" ] && read_mark="x"
      printf '  [%s] %s  %s  from=%s  kind=%-8s  %s\n' "$read_mark" "$id" "$sent" "$from" "$kind" "$preview"
    done
    echo
    echo "show:  agent-inbox show <id>"
    echo "mark:  agent-inbox mark <id>"
    ;;
  show)
    [ -n "$arg" ] || ab_die "show requires <id>"
    target="$(ls "$dir"/*_*_"${arg}".json 2>/dev/null | head -1 || true)"
    [ -n "$target" ] || ab_die "message id not found: $arg"
    cat "$target"
    ;;
  mark)
    [ -n "$arg" ] || ab_die "mark requires <id>"
    target="$(ls "$dir"/*_*_"${arg}".json 2>/dev/null | head -1 || true)"
    [ -n "$target" ] || ab_die "message id not found: $arg"
    touch "$target.read"
    echo "marked read: $(basename "$target")"
    ;;
  clear)
    count="$(ls "$dir"/*.json 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$count" = "0" ]; then echo "inbox '$alias' already empty."; exit 0; fi
    if [ -t 0 ]; then
      printf "delete %s message(s) from inbox '%s'? [y/N] " "$count" "$alias"
      read -r ans
      case "$ans" in y|Y|yes|YES) : ;; *) echo "cancelled."; exit 0 ;; esac
    fi
    rm -f "$dir"/*.json "$dir"/*.json.read
    echo "cleared $count message(s) from inbox '$alias'"
    ;;
esac
