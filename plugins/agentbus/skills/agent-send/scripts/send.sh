#!/usr/bin/env bash
# /agent-send <to> [--from <alias>] [--kind <kind>] [--json | --file <path>] [--strict] <message...>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

to=""
from=""
kind="text"
json_mode=0
file_path=""
strict=0
declare -a rest=()

while [ $# -gt 0 ]; do
  case "$1" in
    --from)    from="$2"; shift 2 ;;
    --kind)    kind="$2"; shift 2 ;;
    --json)    json_mode=1; kind="json"; shift ;;
    --file)    file_path="$2"; shift 2 ;;
    --strict)  strict=1; shift ;;
    --help|-h)
      cat <<EOF
Usage: agent-send <to> [--from <alias>] [--kind <k>] [--json | --file <path>] [--strict] <message>

<to>          recipient alias (e.g. backend) OR raw tmux target (%paneId, sess:win[.pane])
--from        sender alias used in the prefix / mailbox entry (default: auto-detect from current pane registration, else 'unknown')
--kind        free-form kind tag stored in mailbox (default: text; auto 'json' with --json)
--json        treat <message> as JSON body — forces mailbox route
--file <p>    use file contents as body — forces mailbox route, kind defaults to 'file'
--strict      refuse to send if recipient pane's current_command is not a known agent CLI
EOF
      exit 0
      ;;
    -*) ab_die "unknown flag: $1" ;;
    *)
      if [ -z "$to" ]; then to="$1"; else rest+=("$1"); fi
      shift
      ;;
  esac
done

[ -n "$to" ] || ab_die "recipient is required. usage: agent-send <to> [flags] <message>"

# Resolve from-alias from current pane if not provided
if [ -z "$from" ]; then
  self_pane="$(ab_current_pane 2>/dev/null || true)"
  if [ -n "$self_pane" ]; then
    from="$(jq -r --arg p "$self_pane" '[ to_entries[] | select(.value.pane == $p) | .key ] | first // empty' "$REGISTRY" 2>/dev/null || true)"
  fi
  [ -n "$from" ] || from="unknown"
fi

# Resolve body source
body_tmp="$(mktemp -t agentbus-body.XXXXXX)"
trap 'rm -f "$body_tmp"' EXIT

if [ -n "$file_path" ]; then
  [ -f "$file_path" ] || ab_die "file not found: $file_path"
  if [ ${#rest[@]} -gt 0 ]; then
    # message comes first as a label, then file contents
    printf '%s\n\n--- file: %s ---\n' "${rest[*]}" "$file_path" > "$body_tmp"
    cat "$file_path" >> "$body_tmp"
  else
    cp "$file_path" "$body_tmp"
  fi
  [ "$kind" = "text" ] && kind="file"
elif [ ${#rest[@]} -gt 0 ]; then
  printf '%s' "${rest[*]}" > "$body_tmp"
else
  # read from stdin
  if [ -t 0 ]; then
    ab_die "no message given (use args, --file, or pipe via stdin)"
  fi
  cat > "$body_tmp"
fi

flags=()
[ "$json_mode" -eq 1 ] && flags+=(--json)
[ -n "$file_path" ] && flags+=(--file)
[ "$strict" -eq 1 ] && flags+=(--strict)

ab_send "$to" "$from" "$kind" "$body_tmp" "${flags[@]}"
