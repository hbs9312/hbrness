#!/usr/bin/env bash
# agentbus shared library — registry R/W, tmux helpers, send dispatch
#
# Storage (Tier 1):
#   $AGENTBUS_HOME/registry.json
#   $AGENTBUS_HOME/inbox/<alias>/<TS>_<from>_<id>.json
#
# Source-only: scripts should `source` this then call functions.

set -u

AGENTBUS_HOME="${AGENTBUS_HOME:-$HOME/.hbrness/agentbus}"
REGISTRY="$AGENTBUS_HOME/registry.json"
INBOX_ROOT="$AGENTBUS_HOME/inbox"
LOCK_FILE="$AGENTBUS_HOME/.lock"

DIRECT_THRESHOLD="${AGENTBUS_DIRECT_THRESHOLD:-500}"

ab_init_home() {
  mkdir -p "$AGENTBUS_HOME" "$INBOX_ROOT"
  [ -f "$REGISTRY" ] || printf '{}\n' > "$REGISTRY"
}

ab_die() { printf 'agentbus: %s\n' "$*" >&2; exit 1; }
ab_log() { printf 'agentbus: %s\n' "$*" >&2; }

ab_need() {
  command -v "$1" >/dev/null 2>&1 || ab_die "required command not found: $1"
}

ab_need_jq() { ab_need jq; }
ab_need_tmux() { ab_need tmux; }

# ─────────────────────────────────────────────────────────────────────────────
# Locking — flock if available, fall back to mkdir
# ─────────────────────────────────────────────────────────────────────────────

ab_with_lock() {
  ab_init_home
  if command -v flock >/dev/null 2>&1; then
    (
      exec 9>"$LOCK_FILE"
      flock -w 5 9 || ab_die "lock timeout on $LOCK_FILE"
      "$@"
    )
  else
    local i=0
    while ! mkdir "${LOCK_FILE}.d" 2>/dev/null; do
      i=$((i+1))
      [ "$i" -gt 50 ] && ab_die "lock timeout on $LOCK_FILE"
      sleep 0.1
    done
    trap 'rmdir "${LOCK_FILE}.d" 2>/dev/null || true' EXIT
    "$@"
    rmdir "${LOCK_FILE}.d" 2>/dev/null || true
    trap - EXIT
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# tmux context detection
# ─────────────────────────────────────────────────────────────────────────────

ab_current_pane() {
  if [ -n "${TMUX_PANE:-}" ]; then
    printf '%s\n' "$TMUX_PANE"
  elif [ -n "${TMUX:-}" ]; then
    tmux display-message -p '#{pane_id}'
  else
    return 1
  fi
}

ab_pane_info() {
  # echo "<session>|<window>|<pane>|<command>|<pid>" for given pane id
  local pane="$1"
  tmux display-message -p -t "$pane" \
    '#{session_name}|#{window_index}|#{pane_id}|#{pane_current_command}|#{pane_pid}' \
    2>/dev/null
}

ab_pane_exists() {
  local pane="$1"
  tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -Fxq "$pane"
}

# ─────────────────────────────────────────────────────────────────────────────
# Codex / Claude submit-mode detection (copied from planflow helper-server)
# ─────────────────────────────────────────────────────────────────────────────

ab_is_codex_session() {
  [ -n "${CODEX_THREAD_ID:-}" ] || [ -n "${CODEX_CI:-}" ] || [ -n "${CODEX_SANDBOX:-}" ]
}

ab_tmux_submit() {
  local pane="$1"
  local mode="${AGENTBUS_TMUX_SUBMIT_MODE:-}"
  if [ -z "$mode" ]; then
    if ab_is_codex_session; then
      mode="codex-enhanced-enter"
    else
      mode="Enter"
    fi
  fi
  if [ "$mode" = "codex-enhanced-enter" ]; then
    # CSI-u plain Enter for codex TUI with enhanced keyboard reporting
    tmux send-keys -t "$pane" -l $'\e[13;1u'
  else
    tmux send-keys -t "$pane" "$mode"
  fi
}

ab_tmux_send_line() {
  # Send one line of literal text + submit. Strips embedded newlines.
  local pane="$1"
  local text="$2"
  # Strip CR/LF, cap absurd lengths so we don't wedge tmux's command buffer.
  text="$(printf '%s' "$text" | tr -d '\r\n' )"
  if [ "${#text}" -gt 4000 ]; then
    text="${text:0:4000}…(truncated)"
  fi
  tmux send-keys -t "$pane" -l "$text"
  ab_tmux_submit "$pane"
}

# ─────────────────────────────────────────────────────────────────────────────
# Registry operations (atomic via lock)
# ─────────────────────────────────────────────────────────────────────────────

_ab_registry_write() {
  # stdin: new JSON. Writes atomically.
  local tmp
  tmp="$(mktemp "$REGISTRY.XXXXXX")"
  cat > "$tmp"
  mv "$tmp" "$REGISTRY"
}

ab_registry_get() {
  # ab_registry_get <alias> → prints JSON object or empty
  ab_init_home
  jq -r --arg a "$1" '.[$a] // empty | tojson' "$REGISTRY" 2>/dev/null
}

ab_registry_put() {
  # ab_registry_put <alias> <session> <window> <pane> <tool> <pid>
  local alias="$1" session="$2" window="$3" pane="$4" tool="$5" pid="$6"
  ab_with_lock bash -c "
    jq --arg a '$alias' \
       --arg s '$session' \
       --argjson w $window \
       --arg p '$pane' \
       --arg t '$tool' \
       --argjson pid $pid \
       --arg ts '$(date -u +%Y-%m-%dT%H:%M:%SZ)' \
       '.[\$a] = { session: \$s, window: \$w, pane: \$p, tool: \$t, pid: \$pid, registered_at: \$ts }' \
       '$REGISTRY' | { tmp=\$(mktemp '$REGISTRY.XXXXXX'); cat > \"\$tmp\"; mv \"\$tmp\" '$REGISTRY'; }
  "
}

ab_registry_remove_alias() {
  ab_with_lock bash -c "
    jq --arg a '$1' 'del(.[\$a])' '$REGISTRY' | \
      { tmp=\$(mktemp '$REGISTRY.XXXXXX'); cat > \"\$tmp\"; mv \"\$tmp\" '$REGISTRY'; }
  "
}

ab_registry_remove_by_pane() {
  # remove all entries whose pane matches
  ab_with_lock bash -c "
    jq --arg p '$1' 'with_entries(select(.value.pane != \$p))' '$REGISTRY' | \
      { tmp=\$(mktemp '$REGISTRY.XXXXXX'); cat > \"\$tmp\"; mv \"\$tmp\" '$REGISTRY'; }
  "
}

ab_registry_prune_stale() {
  # Remove entries whose pane no longer exists. Prints removed aliases.
  ab_init_home
  local live
  live="$(tmux list-panes -a -F '#{pane_id}' 2>/dev/null | tr '\n' ' ')"
  local removed
  removed="$(jq -r --arg live " $live " '
    to_entries
    | map(select((" " + .value.pane + " ") as $needle | $live | contains($needle) | not))
    | .[].key
  ' "$REGISTRY" 2>/dev/null)"
  if [ -n "$removed" ]; then
    ab_with_lock bash -c "
      jq --arg live ' $live ' 'with_entries(select(\" \" + .value.pane + \" \" as \$n | \$live | contains(\$n)))' \
        '$REGISTRY' | { tmp=\$(mktemp '$REGISTRY.XXXXXX'); cat > \"\$tmp\"; mv \"\$tmp\" '$REGISTRY'; }
    "
  fi
  printf '%s\n' "$removed"
}

ab_registry_list() {
  ab_init_home
  jq -r '
    to_entries
    | sort_by(.key)
    | .[]
    | "\(.key)\t\(.value.session):\(.value.window)\t\(.value.pane)\t\(.value.tool)\tpid=\(.value.pid)\tregistered=\(.value.registered_at)"
  ' "$REGISTRY" 2>/dev/null
}

# ─────────────────────────────────────────────────────────────────────────────
# Recipient resolution — alias or raw tmux target
# ─────────────────────────────────────────────────────────────────────────────

ab_resolve_recipient() {
  # Input: alias OR raw target (%paneId, session:window, session:window.pane)
  # Output (stdout): "<resolved-pane-id>|<display-name>"
  local target="$1"
  ab_init_home

  # Try alias first
  local entry
  entry="$(jq -r --arg a "$target" '.[$a] // empty' "$REGISTRY" 2>/dev/null)"
  if [ -n "$entry" ] && [ "$entry" != "null" ]; then
    local pane
    pane="$(printf '%s' "$entry" | jq -r '.pane')"
    if ab_pane_exists "$pane"; then
      printf '%s|alias:%s\n' "$pane" "$target"
      return 0
    else
      ab_log "alias '$target' points to stale pane $pane — pruning"
      ab_registry_remove_alias "$target"
      return 1
    fi
  fi

  # Treat as raw target. Two shapes: %paneId  or  session:window[.pane]
  if [[ "$target" == %* ]]; then
    if ab_pane_exists "$target"; then
      printf '%s|raw:%s\n' "$target" "$target"
      return 0
    fi
    return 1
  fi

  # session:window[.pane] → resolve to %paneId
  local pane_id
  pane_id="$(tmux display-message -p -t "$target" '#{pane_id}' 2>/dev/null)" || return 1
  [ -n "$pane_id" ] || return 1
  printf '%s|raw:%s\n' "$pane_id" "$target"
}

# ─────────────────────────────────────────────────────────────────────────────
# Inbox file operations
# ─────────────────────────────────────────────────────────────────────────────

ab_msg_id() {
  # short random id
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 3
  else
    printf '%04x%02x' $((RANDOM)) $((RANDOM % 256))
  fi
}

ab_inbox_write() {
  # ab_inbox_write <to-alias-or-display> <from> <id> <kind> <body-file>
  # echoes the resulting path on stdout
  local to="$1" from="$2" id="$3" kind="$4" body_file="$5"
  local dir="$INBOX_ROOT/$to"
  mkdir -p "$dir"
  local ts
  ts="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
  local path="$dir/${ts}_${from}_${id}.json"

  jq -n \
    --arg id "$id" \
    --arg from "$from" \
    --arg to "$to" \
    --arg sent_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg kind "$kind" \
    --rawfile body "$body_file" \
    '{
       id: $id,
       from: $from,
       to: $to,
       sent_at: $sent_at,
       kind: $kind,
       body: $body,
       broadcast_group: null,
       recipients: null
     }' > "$path"
  printf '%s\n' "$path"
}

# ─────────────────────────────────────────────────────────────────────────────
# Send dispatch — direct vs mailbox by length / flags
# ─────────────────────────────────────────────────────────────────────────────

ab_send() {
  # ab_send <to> <from> <kind> <body-file> [--json|--file] [--strict]
  local to="$1" from="$2" kind="$3" body_file="$4"; shift 4
  local force_mailbox=0 strict=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --json|--file) force_mailbox=1 ;;
      --strict) strict=1 ;;
    esac
    shift
  done

  ab_need_jq
  ab_need_tmux
  ab_init_home

  local resolved
  resolved="$(ab_resolve_recipient "$to")" || ab_die "unknown recipient: $to (not an alias, not an active pane/target)"
  local pane="${resolved%%|*}"
  local display="${resolved##*|}"

  # self-send guard
  local self_pane
  self_pane="$(ab_current_pane 2>/dev/null || true)"
  if [ -n "$self_pane" ] && [ "$self_pane" = "$pane" ]; then
    ab_die "refusing to send to self ($pane)"
  fi

  # strict mode: receiving pane should be running a known interactive agent
  if [ "$strict" -eq 1 ]; then
    local info cmd
    info="$(ab_pane_info "$pane" || true)"
    cmd="$(printf '%s' "$info" | awk -F'|' '{print $4}')"
    case "$cmd" in
      claude|codex|node|python|python3|sh|bash|zsh) : ;;
      *) ab_die "strict: pane $pane current_command='$cmd' — not a known agent CLI" ;;
    esac
  fi

  local body_len
  body_len="$(wc -c < "$body_file" | tr -d ' ')"

  local id; id="$(ab_msg_id)"
  local route

  if [ "$force_mailbox" -eq 1 ] || [ "$body_len" -ge "$DIRECT_THRESHOLD" ]; then
    route="mailbox"
    local path
    path="$(ab_inbox_write "$to" "$from" "$id" "$kind" "$body_file")"
    local notice="[agentbus] new message from ${from} (kind=${kind}, id=${id}): ${path} — Read 로 열어서 확인해줘."
    ab_tmux_send_line "$pane" "$notice"
    printf '{"route":"mailbox","id":"%s","path":"%s","recipient":"%s","display":"%s"}\n' \
      "$id" "$path" "$pane" "$display"
  else
    route="direct"
    local body
    body="$(cat "$body_file")"
    local stamp
    stamp="$(date +%H:%M)"
    local line="[from ${from} @ ${stamp}] ${body}"
    ab_tmux_send_line "$pane" "$line"
    printf '{"route":"direct","id":"%s","bytes":%s,"recipient":"%s","display":"%s"}\n' \
      "$id" "$body_len" "$pane" "$display"
  fi
}
