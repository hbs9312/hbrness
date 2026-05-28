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

_ab_lock_diagnose() {
  # Build a diagnostic for a lock timeout. Distinguish:
  #   - permission/ownership problem under $AGENTBUS_HOME
  #   - stale lock (file/dir exists, no live holder we can see)
  #   - genuine contention (something else is holding it right now)
  local lock_path="$1" kind="$2"  # kind: file (flock) | dir (mkdir)
  if [ ! -w "$AGENTBUS_HOME" ] 2>/dev/null; then
    printf 'lock timeout on %s: %s is not writable (check ownership/permission)\n' \
      "$lock_path" "$AGENTBUS_HOME"
    return
  fi
  case "$kind" in
    file)
      if [ ! -e "$lock_path" ]; then
        printf 'lock timeout on %s: lock file disappeared mid-wait — retry; if it persists, another agentbus process may be racing\n' "$lock_path"
      else
        printf 'lock timeout on %s: another agentbus command is holding it, or the lock is stuck. Retry; if it persists, remove the file (no agentbus must be running)\n' "$lock_path"
      fi
      ;;
    dir)
      if [ -d "$lock_path" ]; then
        printf 'lock timeout on %s: lock dir exists — likely stale from a prior crash. If no agentbus is running, `rmdir %s` and retry\n' "$lock_path" "$lock_path"
      else
        printf 'lock timeout on %s: could not create lock dir (permission or race). Check %s\n' "$lock_path" "$AGENTBUS_HOME"
      fi
      ;;
    *)
      printf 'lock timeout on %s\n' "$lock_path"
      ;;
  esac
}

ab_with_lock() {
  ab_init_home
  if command -v flock >/dev/null 2>&1; then
    (
      if ! exec 9>"$LOCK_FILE" 2>/dev/null; then
        ab_die "cannot open lock file $LOCK_FILE: check $AGENTBUS_HOME ownership/permission"
      fi
      if ! flock -w 5 9; then
        ab_die "$(_ab_lock_diagnose "$LOCK_FILE" file)"
      fi
      "$@"
    )
  else
    local i=0
    while ! mkdir "${LOCK_FILE}.d" 2>/dev/null; do
      i=$((i+1))
      if [ "$i" -gt 50 ]; then
        ab_die "$(_ab_lock_diagnose "${LOCK_FILE}.d" dir)"
      fi
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
#
# All tmux query helpers populate AB_TMUX_LAST_ERR (stderr from the failing
# command) when they fail so callers can distinguish:
#   - the pane truly does not exist (server reachable, target missing), vs
#   - the tmux server / socket is unreachable, vs
#   - the sandbox/sandboxing layer blocks access (Operation not permitted), vs
#   - tmux binary missing or not in a tmux session at all.
# ─────────────────────────────────────────────────────────────────────────────

AB_TMUX_LAST_ERR=""
# Subshell-safe spillover. Command substitution puts callees in a subshell so
# changes to AB_TMUX_LAST_ERR don't leak back to the parent. We mirror the
# captured stderr to this file inside $AGENTBUS_HOME so the parent process can
# still recover the diagnostic.
_AB_TMUX_ERR_FILE_BASENAME=".last-tmux-err"

_ab_tmux_err_file() {
  printf '%s/%s\n' "$AGENTBUS_HOME" "$_AB_TMUX_ERR_FILE_BASENAME"
}

_ab_tmux_err_set() {
  AB_TMUX_LAST_ERR="$1"
  if [ -d "$AGENTBUS_HOME" ]; then
    printf '%s' "$1" > "$(_ab_tmux_err_file)" 2>/dev/null || true
  fi
}

_ab_tmux_err_load() {
  # If in-process var is empty, try the spillover file.
  if [ -z "${AB_TMUX_LAST_ERR:-}" ]; then
    local f; f="$(_ab_tmux_err_file)"
    if [ -s "$f" ]; then
      AB_TMUX_LAST_ERR="$(cat "$f" 2>/dev/null || true)"
    fi
  fi
}

_ab_tmux_err_clear() {
  AB_TMUX_LAST_ERR=""
  if [ -d "$AGENTBUS_HOME" ]; then
    rm -f "$(_ab_tmux_err_file)" 2>/dev/null || true
  fi
}

ab_classify_tmux_err() {
  # Classify a captured stderr string. Echoes one of:
  #   denied | no-server | missing-target | unknown
  local err="$1"
  case "$err" in
    *"Operation not permitted"*|*"operation not permitted"*) printf 'denied' ;;
    *"Permission denied"*|*"permission denied"*) printf 'denied' ;;
    *"EPERM"*) printf 'denied' ;;
    *"sandbox"*|*"Sandbox"*) printf 'denied' ;;
    *"no server running"*|*"failed to connect"*|*"no current server"*|*"server exited"*) printf 'no-server' ;;
    *"can't find"*|*"cannot find"*|*"no such pane"*|*"pane not found"*|*"target not found"*|*"unknown target"*|*"window not found"*|*"session not found"*|*"bad window"*) printf 'missing-target' ;;
    *"error connecting to"*)
      # Server-socket connect failures. Some ship as EPERM under sandbox; the
      # explicit EPERM/permission cases above already match, so this means a
      # plain connect failure (typically ENOENT — server not running).
      printf 'no-server' ;;
    *) printf 'unknown' ;;
  esac
}

ab_tmux_access_message() {
  # Human-readable message for the most recent tmux access failure.
  # Pulls from AB_TMUX_LAST_ERR; if empty (we're in a parent after a
  # subshell-only failure), loads from the spillover file.
  _ab_tmux_err_load
  local err="${AB_TMUX_LAST_ERR:-}"
  local kind; kind="$(ab_classify_tmux_err "$err")"
  case "$kind" in
    denied)
      if [ -n "$err" ]; then
        printf 'cannot query tmux panes: %s. Re-run with tmux access (escalated permission, or outside the Codex sandbox).' "$err"
      else
        printf 'cannot query tmux panes: access denied. Re-run with tmux access (escalated permission, or outside the Codex sandbox).'
      fi
      ;;
    no-server)
      printf 'cannot query tmux: tmux server not reachable (%s). Start a tmux session first.' "${err:-unknown}"
      ;;
    missing-target)
      printf 'cannot query tmux: %s' "$err"
      ;;
    *)
      if [ -n "$err" ]; then
        printf 'cannot query tmux: %s' "$err"
      else
        printf 'cannot query tmux (no error captured)'
      fi
      ;;
  esac
}

ab_die_tmux_or() {
  # If AB_TMUX_LAST_ERR is populated, die with the access-error explanation.
  # Otherwise die with the given fallback message.
  if [ -n "${AB_TMUX_LAST_ERR:-}" ]; then
    ab_die "$(ab_tmux_access_message)"
  else
    ab_die "$1"
  fi
}

_ab_tmux_run() {
  # Run a tmux subcommand, capture stdout + stderr separately.
  # Usage: _ab_tmux_run <stdout-var-name> <args...>
  # On rc != 0, writes the stderr line into both AB_TMUX_LAST_ERR (in-process)
  # and the spillover file (so parent processes past a subshell can recover
  # the diagnostic). Returns the tmux rc.
  local __out_var="$1"; shift
  _ab_tmux_err_clear
  if ! command -v tmux >/dev/null 2>&1; then
    _ab_tmux_err_set "tmux: command not found"
    return 127
  fi
  local __err_file __out __rc
  __err_file="$(mktemp -t agentbus-tmux.XXXXXX)" || {
    _ab_tmux_err_set "cannot create temp file for tmux stderr capture"
    return 1
  }
  __out="$(tmux "$@" 2>"$__err_file")"
  __rc=$?
  if [ $__rc -ne 0 ]; then
    local __err_line
    __err_line="$(tr -d '\r' < "$__err_file" | awk 'NF{print; exit}')"
    [ -z "$__err_line" ] && __err_line="(tmux exit $__rc, no stderr)"
    _ab_tmux_err_set "$__err_line"
  fi
  rm -f "$__err_file"
  # Assign to caller's var name.
  printf -v "$__out_var" '%s' "$__out"
  return $__rc
}

ab_current_pane() {
  # Resolve current pane id. Returns:
  #   0 — echoed pane id on stdout
  #   1 — not inside a tmux session at all (and TMUX_PANE unset)
  #   2 — TMUX_PANE/TMUX claim a session but tmux query failed (access issue)
  if [ -n "${TMUX_PANE:-}" ]; then
    printf '%s\n' "$TMUX_PANE"
    return 0
  fi
  if [ -z "${TMUX:-}" ]; then
    return 1
  fi
  local out
  if _ab_tmux_run out display-message -p '#{pane_id}'; then
    printf '%s\n' "$out"
    return 0
  fi
  return 2
}

ab_pane_info() {
  # Echo "<session>|<window>|<pane>|<command>|<pid>" for given pane id.
  # Returns 0 on success, non-zero on failure. AB_TMUX_LAST_ERR set on failure.
  local pane="$1" out
  if _ab_tmux_run out display-message -p -t "$pane" \
       '#{session_name}|#{window_index}|#{pane_id}|#{pane_current_command}|#{pane_pid}'; then
    printf '%s\n' "$out"
    return 0
  fi
  return 1
}

ab_pane_status() {
  # Three-state pane probe. Returns:
  #   0 — pane exists (server reachable, target found)
  #   1 — pane confirmed missing (server reachable, target not found)
  #   2 — could not determine (server unreachable, access denied, etc.)
  # On rc=2, AB_TMUX_LAST_ERR carries the diagnostic.
  local pane="$1" out
  if _ab_tmux_run out display-message -p -t "$pane" '#{pane_id}'; then
    if [ "$out" = "$pane" ]; then
      return 0
    fi
    return 1
  fi
  case "$(ab_classify_tmux_err "$AB_TMUX_LAST_ERR")" in
    missing-target) _ab_tmux_err_clear; return 1 ;;
    *) return 2 ;;
  esac
}

# Backward-compatible boolean wrapper. NOTE: this collapses "missing" and
# "cannot determine" into the same falsy result; new code should use
# ab_pane_status to handle the access-denied case correctly.
ab_pane_exists() {
  ab_pane_status "$1"
  [ $? -eq 0 ]
}

# ─────────────────────────────────────────────────────────────────────────────
# Codex / Claude submit-mode detection (copied from planflow helper-server)
# ─────────────────────────────────────────────────────────────────────────────

ab_is_codex_session() {
  [ -n "${CODEX_THREAD_ID:-}" ] || [ -n "${CODEX_CI:-}" ] || [ -n "${CODEX_SANDBOX:-}" ]
}

ab_tmux_submit() {
  # Submit-mode is chosen by *recipient* tool, not sender — a claude pane
  # sending to a codex pane must still emit CSI-u so codex's enhanced
  # keyboard reporting accepts it. Sender env is only a legacy fallback.
  local pane="$1"
  local recipient_tool="${2:-}"
  local mode="${AGENTBUS_TMUX_SUBMIT_MODE:-}"
  if [ -z "$mode" ]; then
    case "$recipient_tool" in
      codex) mode="codex-enhanced-enter" ;;
      claude|node|shell|bash|sh|zsh|python|python3) mode="Enter" ;;
      *)
        if ab_is_codex_session; then
          mode="codex-enhanced-enter"
        else
          mode="Enter"
        fi
        ;;
    esac
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
  local recipient_tool="${3:-}"
  # Strip CR/LF, cap absurd lengths so we don't wedge tmux's command buffer.
  text="$(printf '%s' "$text" | tr -d '\r\n' )"
  if [ "${#text}" -gt 4000 ]; then
    text="${text:0:4000}…(truncated)"
  fi
  tmux send-keys -t "$pane" -l "$text"
  ab_tmux_submit "$pane" "$recipient_tool"
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
  # Remove entries whose pane no longer exists. Prints removed aliases on stdout.
  # Returns:
  #   0 — query succeeded (prune may or may not have removed anything)
  #   2 — could not query tmux (AB_TMUX_LAST_ERR set); registry left untouched
  ab_init_home
  local out
  if ! _ab_tmux_run out list-panes -a -F '#{pane_id}'; then
    return 2
  fi
  # Build " %a %b %c " — leading AND trailing space matter for the
  # substring-contains check below. Command substitution strips the trailing
  # newline that `tr` produced, so we re-append it explicitly.
  local live=" $(printf '%s' "$out" | tr '\n' ' ')"
  case "$live" in
    *' ') : ;;
    *)    live="$live " ;;
  esac
  local removed
  removed="$(jq -r --arg live "$live" '
    to_entries
    | map(select((" " + .value.pane + " ") as $needle | $live | contains($needle) | not))
    | .[].key
  ' "$REGISTRY" 2>/dev/null)"
  if [ -n "$removed" ]; then
    # NB: parentheses around the string concat are REQUIRED here. Without them
    # jq parses `" " + .value.pane + " " as $n | …` with `as` binding tighter
    # than `+`, ending up trying to add a boolean ("contains" result) to a
    # string. The parens force `(" " + .value.pane + " ") as $n | …`.
    ab_with_lock bash -c "
      jq --arg live '$live' 'with_entries(select((\" \" + .value.pane + \" \") as \$n | \$live | contains(\$n)))' \
        '$REGISTRY' | { tmp=\$(mktemp '$REGISTRY.XXXXXX'); cat > \"\$tmp\"; mv \"\$tmp\" '$REGISTRY'; }
    "
  fi
  printf '%s\n' "$removed"
  return 0
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

_ab_detect_tool_by_pane() {
  # Best-effort tool detection from live pane_current_command. Used when the
  # registry has no entry (raw target) or its tool field is unusable.
  local pane="$1"
  local info cmd
  info="$(ab_pane_info "$pane" 2>/dev/null || true)"
  cmd="$(printf '%s' "$info" | awk -F'|' '{print $4}')"
  case "$cmd" in
    claude) printf 'claude' ;;
    codex)  printf 'codex' ;;
    node)   printf 'claude' ;;   # claude CLI wrapper on some installs
    "")     printf 'unknown' ;;
    *)
      # Version-string like "2.1.153" — claude CLI on recent installs.
      if [[ "$cmd" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]; then
        printf 'claude'
      else
        printf '%s' "$cmd"
      fi
      ;;
  esac
}

_ab_normalize_tool() {
  # If the registry-recorded tool is one of the known interactive agents,
  # trust it. Otherwise fall back to a live detection from the pane.
  local tool="$1" pane="$2"
  case "$tool" in
    claude|codex|shell|node|bash|sh|zsh|python|python3) printf '%s' "$tool" ;;
    *) _ab_detect_tool_by_pane "$pane" ;;
  esac
}

ab_resolve_recipient() {
  # Input: alias OR raw target (%paneId, session:window, session:window.pane)
  # Output (stdout): "<resolved-pane-id>|<display-name>|<tool>"
  # Returns:
  #   0 — resolved (stdout populated)
  #   1 — recipient not found (alias unknown, or pane confirmed missing)
  #   2 — tmux query failed (access denied / server unreachable);
  #       AB_TMUX_LAST_ERR carries the diagnostic, registry NOT modified.
  local target="$1"
  ab_init_home

  # Try alias first
  local entry
  entry="$(jq -r --arg a "$target" '.[$a] // empty' "$REGISTRY" 2>/dev/null)"
  if [ -n "$entry" ] && [ "$entry" != "null" ]; then
    local pane tool rc=0
    pane="$(printf '%s' "$entry" | jq -r '.pane')"
    tool="$(printf '%s' "$entry" | jq -r '.tool // empty')"
    ab_pane_status "$pane" || rc=$?
    case $rc in
      0)
        tool="$(_ab_normalize_tool "$tool" "$pane")"
        printf '%s|alias:%s|%s\n' "$pane" "$target" "$tool"
        return 0
        ;;
      1)
        ab_log "alias '$target' points to stale pane $pane — pruning"
        ab_registry_remove_alias "$target"
        return 1
        ;;
      2)
        return 2
        ;;
    esac
  fi

  # Treat as raw target. Two shapes: %paneId  or  session:window[.pane]
  if [[ "$target" == %* ]]; then
    local rc=0
    ab_pane_status "$target" || rc=$?
    case $rc in
      0)
        local tool
        tool="$(_ab_detect_tool_by_pane "$target")"
        printf '%s|raw:%s|%s\n' "$target" "$target" "$tool"
        return 0
        ;;
      1) return 1 ;;
      2) return 2 ;;
    esac
  fi

  # session:window[.pane] → resolve to %paneId
  local pane_id
  if ! _ab_tmux_run pane_id display-message -p -t "$target" '#{pane_id}'; then
    case "$(ab_classify_tmux_err "$AB_TMUX_LAST_ERR")" in
      missing-target) _ab_tmux_err_clear; return 1 ;;
      *) return 2 ;;
    esac
  fi
  [ -n "$pane_id" ] || return 1
  local tool
  tool="$(_ab_detect_tool_by_pane "$pane_id")"
  printf '%s|raw:%s|%s\n' "$pane_id" "$target" "$tool"
  return 0
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

  local resolved rrc=0
  resolved="$(ab_resolve_recipient "$to")" || rrc=$?
  if [ $rrc -ne 0 ]; then
    if [ $rrc -eq 2 ]; then
      ab_die "$(ab_tmux_access_message)"
    fi
    ab_die "unknown recipient: $to (not an alias, not an active pane/target)"
  fi
  # Format: "<pane>|<display>|<tool>"
  local pane display tool
  pane="$(printf '%s' "$resolved" | awk -F'|' '{print $1}')"
  display="$(printf '%s' "$resolved" | awk -F'|' '{print $2}')"
  tool="$(printf '%s' "$resolved" | awk -F'|' '{print $3}')"

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
    ab_tmux_send_line "$pane" "$notice" "$tool"
    printf '{"route":"mailbox","id":"%s","path":"%s","recipient":"%s","display":"%s","tool":"%s"}\n' \
      "$id" "$path" "$pane" "$display" "$tool"
  else
    route="direct"
    local body
    body="$(cat "$body_file")"
    local stamp
    stamp="$(date +%H:%M)"
    local line="[from ${from} @ ${stamp}] ${body}"
    ab_tmux_send_line "$pane" "$line" "$tool"
    printf '{"route":"direct","id":"%s","bytes":%s,"recipient":"%s","display":"%s","tool":"%s"}\n' \
      "$id" "$body_len" "$pane" "$display" "$tool"
  fi
}
