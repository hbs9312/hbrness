#!/usr/bin/env bash
# xreview:live shared library — background-review session helpers (tmux / orca).
#
# Storage (Tier 1, namespaced under live/):
#   $XRLIVE_HOME/<repo-key>/<slug>/REVIEW_REQUEST.md
#   $XRLIVE_HOME/<repo-key>/<slug>/REVIEW_RESULT.md
#   $XRLIVE_HOME/<repo-key>/<slug>/meta.json
#   $XRLIVE_HOME/.sessions/<slug>.json     (flat index for status/stop)
#
# A "reviewer" agent runs in its own background session named `xrev-<slug>` —
# a detached tmux session, or an Orca terminal tab. The launcher pane only sees
# a completion ping; peek/dock show that session without disturbing it.
#
# Source-only: scripts should `source` this then call functions.

set -u

XRLIVE_HOME="${XRLIVE_HOME:-$HOME/.hbrness/xreview/live}"
XRLIVE_SESSIONS="$XRLIVE_HOME/.sessions"
XRLIVE_SESSION_PREFIX="xrev-"

xr_die() { printf 'xreview:live: %s\n' "$*" >&2; exit 1; }
xr_log() { printf 'xreview:live: %s\n' "$*" >&2; }
xr_need() { command -v "$1" >/dev/null 2>&1 || xr_die "required command not found: $1"; }

xr_init_home() {
  mkdir -p "$XRLIVE_HOME" "$XRLIVE_SESSIONS"
}

# ─────────────────────────────────────────────────────────────────────────────
# Terminal backend — tmux or orca
#
# xreview needs six things from whatever owns the terminals: spawn a detached
# reviewer, say whether it is alive, type a line into a pane, read the rendered
# screen, kill it, and show it to the user. tmux and Orca both offer all six, so
# everything dispatches through the xr_be_* helpers below and nothing outside
# this section calls `tmux` or `orca` directly.
#
#   session ref : tmux → session name `xrev-<slug>`, orca → terminal handle
#   launcher id : tmux → $TMUX_PANE,                 orca → $ORCA_TERMINAL_HANDLE
#
# Every session records its backend in the index, so a review started under tmux
# stays listable from an Orca session (status/stop fall back to the durable
# files instead of dying).
# ─────────────────────────────────────────────────────────────────────────────

# Which backend owns THIS shell. tmux wins when both look present: nesting runs
# tmux inside an Orca tab, and the launcher we ping back is then the tmux pane.
xr_backend() {
  if [ -z "${XR_BACKEND:-}" ]; then
    if [ -n "${XRLIVE_BACKEND:-}" ]; then      XR_BACKEND="$XRLIVE_BACKEND"
    elif [ -n "${TMUX_PANE:-}" ] || [ -n "${TMUX:-}" ]; then XR_BACKEND=tmux
    elif [ -n "${ORCA_TERMINAL_HANDLE:-}" ]; then XR_BACKEND=orca
    else XR_BACKEND=none
    fi
  fi
  printf '%s' "$XR_BACKEND"
}

# Can <backend> be driven from here? A session started under the other one is
# still listed, just not controllable.
xr_be_usable() {
  case "${1:-}" in
    tmux) command -v tmux >/dev/null 2>&1 && { [ -n "${TMUX_PANE:-}" ] || [ -n "${TMUX:-}" ]; } ;;
    orca) command -v orca >/dev/null 2>&1 ;;
    *) return 1 ;;
  esac
}

xr_backend_require() {
  local be; be="$(xr_backend)"
  case "$be" in
    tmux) xr_need tmux ;;
    orca) xr_need orca ;;
    *) xr_die "no terminal backend found — start tmux, or run inside Orca. (force one with XRLIVE_BACKEND=tmux|orca)" ;;
  esac
  xr_be_usable "$be" || xr_die "backend '$be' is not usable from this shell"
}

# This pane/terminal, so the watcher knows where to send the completion ping.
xr_launcher_id() {
  case "$(xr_backend)" in
    tmux)
      if [ -n "${TMUX_PANE:-}" ]; then printf '%s' "$TMUX_PANE"; return 0; fi
      tmux display-message -p '#{pane_id}' 2>/dev/null ;;
    orca) printf '%s' "${ORCA_TERMINAL_HANDLE:-}" ;;
  esac
}

xr_session_name() { printf '%s%s' "$XRLIVE_SESSION_PREFIX" "$1"; }

# Run an orca CLI call and apply <jq-filter> to its .result, or echo nothing and
# fail when the call itself failed.
xr_orca_json() {
  local filter="$1"; shift
  "$@" --json 2>/dev/null | jq -er "if .ok then (.result | ${filter}) else empty end" 2>/dev/null
}

# Spawn the reviewer detached. Echoes the session ref the other helpers take.
#   xr_be_spawn <slug> <work-dir> <repo-root> <command>
xr_be_spawn() {
  local slug="$1" work="$2" root="$3" cmd="$4" sess ref
  sess="$(xr_session_name "$slug")"
  case "$(xr_backend)" in
    tmux)
      tmux new-session -d -s "$sess" -x 220 -y 50 -c "$work" "$cmd" || return 1
      # remain-on-exit keeps the pane and its scrollback after the agent exits so
      # peek/dock still show the final state; stop.sh tears it down.
      tmux set-option -t "$sess" remain-on-exit on 2>/dev/null || true
      tmux set-option -t "$sess" window-size manual 2>/dev/null || true
      printf '%s' "$sess" ;;
    orca)
      # Orca terminals belong to a workspace rather than an arbitrary cwd, so the
      # reviewer opens in the repo's worktree and the runner cd's into the scratch
      # dir itself. A repo path Orca does not know falls back to this worktree.
      ref="$(xr_orca_json '.terminal.handle' orca terminal create \
               --worktree "path:$root" --title "$sess" --command "$cmd")" \
        || ref="$(xr_orca_json '.terminal.handle' orca terminal create \
               --worktree current --title "$sess" --command "$cmd")" \
        || return 1
      [ -n "$ref" ] || return 1
      printf '%s' "$ref" ;;
    *) return 1 ;;
  esac
}

# Is the session still there? (The container, not the reviewer process.)
xr_be_alive() {
  local ref="${1:-}" be="${2:-}"
  [ -n "$ref" ] || return 1
  [ -n "$be" ] || be="$(xr_backend)"
  xr_be_usable "$be" || return 1
  case "$be" in
    tmux) tmux has-session -t "=$ref" 2>/dev/null ;;
    orca) [ "$(xr_orca_json '.terminal.connected' orca terminal show --terminal "$ref")" = "true" ] ;;
    *) return 1 ;;
  esac
}

# Has the reviewer PROCESS finished? The runner writes RUN_EXIT with its exit
# code the moment the agent returns, which is the backend-independent signal —
# Orca keeps the shell alive after the command ends, so a live terminal says
# nothing about the review. tmux's dead pane stays as a fallback for sessions
# started before the runner existed.
xr_be_ended() {
  local work="${1:-}" ref="${2:-}" be="${3:-}"
  [ -n "$work" ] && [ -f "$work/RUN_EXIT" ] && return 0
  [ -n "$be" ] || be="$(xr_backend)"
  case "$be" in
    tmux)
      xr_be_usable tmux || return 1
      [ "$(tmux list-panes -t "=$ref" -F '#{pane_dead}' 2>/dev/null | head -1)" = "1" ] ;;
    *) return 1 ;;
  esac
}

# Type a line into a pane and submit it.
xr_be_send() {
  local ref="$1" text="$2" recipient_tool="${3:-}" be="${4:-}"
  [ -n "$be" ] || be="$(xr_backend)"
  text="$(printf '%s' "$text" | tr -d '\r\n')"
  if [ "${#text}" -gt 4000 ]; then text="${text:0:4000}…(truncated)"; fi
  case "$be" in
    tmux)
      tmux send-keys -t "$ref" -l "$text" || return $?
      # codex needs a CSI-u plain Enter (enhanced keyboard reporting) to submit;
      # every other tool takes a plain Enter.
      case "$recipient_tool" in
        codex) tmux send-keys -t "$ref" -l $'\e[13;1u' ;;
        *)     tmux send-keys -t "$ref" Enter ;;
      esac ;;
    orca)
      # Orca submits the prompt itself and reports whether it landed, so the
      # codex CSI-u workaround is not needed here.
      orca terminal send --terminal "$ref" --text "$text" --enter --json >/dev/null 2>&1 ;;
  esac
}

# The visible text of a session's pane. Used to spot a reviewer hung on an
# interactive prompt the detached run cannot answer.
xr_be_capture() {
  local ref="$1" lines="${2:-40}" be="${3:-}"
  [ -n "$be" ] || be="$(xr_backend)"
  case "$be" in
    tmux) tmux capture-pane -p -t "=$ref" 2>/dev/null | tail -n "$lines" ;;
    orca) xr_orca_json '.terminal.tail | join("\n")' \
            orca terminal read --terminal "$ref" --screen --limit "$lines" ;;
  esac
}

xr_be_kill() {
  local ref="${1:-}" be="${2:-}"
  [ -n "$ref" ] || return 0
  [ -n "$be" ] || be="$(xr_backend)"
  xr_be_usable "$be" || return 0
  case "$be" in
    tmux) tmux kill-session -t "=$ref" 2>/dev/null || true ;;
    orca) orca terminal close --terminal "$ref" --tab --json >/dev/null 2>&1 || true ;;
  esac
}

# Close a docked viewport pane. Only tmux has one — under Orca the reviewer tab
# IS the view, so there is nothing separate to close.
xr_be_close_viewport() {
  local vp="${1:-}" be="${2:-}"
  [ -n "$vp" ] || return 1
  [ -n "$be" ] || be="$(xr_backend)"
  case "$be" in
    tmux)
      xr_be_usable tmux || return 1
      tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$vp" || return 1
      tmux kill-pane -t "$vp" 2>/dev/null || true ;;
    *) return 1 ;;
  esac
}

# Backend + session ref recorded for a slug. Sessions written before the backend
# layer carry neither, and were all tmux with the session name as the ref.
xr_slug_backend() {
  local b; b="$(xr_meta "$1" backend 2>/dev/null || true)"
  printf '%s' "${b:-tmux}"
}
xr_slug_ref() {
  local r
  r="$(xr_meta "$1" session_ref 2>/dev/null || true)"
  [ -n "$r" ] || r="$(xr_meta "$1" session 2>/dev/null || true)"
  [ -n "$r" ] || r="$(xr_session_name "$1")"
  printf '%s' "$r"
}

# Return 0 if the given pane text looks like a workspace-trust / permission prompt
# the detached reviewer can't answer (so the run is hung, not progressing). The
# signatures are trust-dialog phrasings unlikely to appear verbatim in a diff;
# callers additionally require RESULT-absent + repeated detection to avoid false
# positives from review prose.
xr_detect_stuck_prompt() {
  printf '%s' "${1:-}" | grep -qiE \
    'trust the files in this folder|trust the contents of|do you trust this (folder|directory|workspace)|allow .* to work in this folder|trust this workspace'
}

# ─────────────────────────────────────────────────────────────────────────────
# Durable watch state — a tiny, single-writer file so consumers can poll the
# review outcome independent of whether the one-shot tmux ping landed. Written
# only by the watcher (notify.sh) + seeded by start.sh; lives beside the work
# files (NOT in the shared .sessions index) to avoid clobbering concurrent
# viewport writes from view.sh.
#   $WORK/WATCH_STATE : line 1 = state token, line 2+ = human detail
#   states: running | done | stuck | ended-no-result | gone | timeout
# ─────────────────────────────────────────────────────────────────────────────
xr_set_watch_state() {
  local work="$1" state="$2" detail="${3:-}"
  [ -n "$work" ] || return 0
  { printf '%s\n' "$state"; [ -n "$detail" ] && printf '%s\n' "$detail"; } \
    > "$work/WATCH_STATE" 2>/dev/null || true
}

# Echo the current watch state token (line 1) for a work dir, or nothing.
xr_get_watch_state() {
  local work="$1"
  [ -n "$work" ] && [ -f "$work/WATCH_STATE" ] || return 1
  head -n1 "$work/WATCH_STATE" 2>/dev/null
}

# ─────────────────────────────────────────────────────────────────────────────
# claude config
# ─────────────────────────────────────────────────────────────────────────────

# Pre-accept Claude Code's workspace-trust dialog for a directory by merging a
# trusted-project entry into the user's ~/.claude.json. The reviewer runs in a
# detached tmux session and can't answer the interactive prompt, so without this
# a claude reviewer hangs on "Do you trust the contents of this directory?". The
# target is a scratch dir this skill just created, so trusting it is safe. No-op
# when jq is unavailable or the merge fails — the reviewer then falls back to the
# dialog (answerable via peek), i.e. never worse than the prior behavior.
xr_claude_pretrust_dir() {
  local dir="$1" cfg tmp
  if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
    cfg="$CLAUDE_CONFIG_DIR/.claude.json"
  else
    cfg="$HOME/.claude.json"
  fi
  command -v jq >/dev/null 2>&1 || return 0
  tmp="$(mktemp)" || return 0
  if [ -f "$cfg" ]; then
    jq --arg d "$dir" '
      .projects = (.projects // {})
      | .projects[$d] = ((.projects[$d] // {})
          + {hasTrustDialogAccepted: true, hasCompletedProjectOnboarding: true})
    ' "$cfg" > "$tmp" 2>/dev/null && mv "$tmp" "$cfg" || rm -f "$tmp"
  else
    mkdir -p "$(dirname "$cfg")" 2>/dev/null || true
    jq -n --arg d "$dir" '
      {projects: {($d): {hasTrustDialogAccepted: true, hasCompletedProjectOnboarding: true}}}
    ' > "$tmp" 2>/dev/null && mv "$tmp" "$cfg" || rm -f "$tmp"
  fi
}

# Codex counterpart of xr_claude_pretrust_dir. Codex tracks workspace trust in
# config.toml as `[projects."<dir>"] trust_level = "trusted"`. A codex reviewer
# runs detached and can't answer "Do you trust the files in this folder?", so
# without this every review (a fresh WORK slug each time) hangs on the trust
# prompt. The target is a scratch dir this skill just created, so trusting it is
# safe. Idempotent (no-op if the entry already exists); no-op on append failure,
# in which case the reviewer falls back to the dialog (answerable via peek).
xr_codex_pretrust_dir() {
  local dir="$1" cfg
  cfg="${CODEX_HOME:-$HOME/.codex}/config.toml"
  # Already trusted? exact section-header match (fixed-string, no regex).
  if [ -f "$cfg" ] && grep -qF "[projects.\"$dir\"]" "$cfg" 2>/dev/null; then
    return 0
  fi
  mkdir -p "$(dirname "$cfg")" 2>/dev/null || true
  # Append a new project table. A table header at EOF is valid TOML regardless
  # of preceding content; the leading newline guarantees separation.
  {
    printf '\n[projects."%s"]\n' "$dir"
    printf 'trust_level = "trusted"\n'
  } >> "$cfg" 2>/dev/null || true
}

# ─────────────────────────────────────────────────────────────────────────────
# Identity / paths
# ─────────────────────────────────────────────────────────────────────────────

xr_opposite_tool() {
  case "$1" in
    claude) printf 'codex' ;;
    codex)  printf 'claude' ;;
    *)      printf 'codex' ;;  # sensible default reviewer
  esac
}

# Resolve a filesystem-safe repo key: owner/repo from origin, else dir basename.
xr_repo_key() {
  local root="$1" url key
  url="$(git -C "$root" remote get-url origin 2>/dev/null || true)"
  if [ -n "$url" ]; then
    key="$(printf '%s' "$url" \
      | sed -E 's#^[^@]+@##; s#^https?://##; s#:#/#; s#\.git$##' \
      | awk -F/ 'NF>=2 {print $(NF-1)"/"$NF}')"
  fi
  [ -n "${key:-}" ] || key="$(basename "$root")"
  printf '%s' "$key" | tr ' ' '_'
}

xr_sanitize() { printf '%s' "$1" | tr '/ ' '__' | tr -cd '[:alnum:]._-'; }

# Resolve a slug from an explicit arg, or auto-pick when exactly one is active.
# Prints slug on stdout; non-zero + diagnostic on stderr when ambiguous/none.
xr_resolve_slug() {
  local arg="${1:-}"
  if [ -n "$arg" ]; then
    arg="${arg#"$XRLIVE_SESSION_PREFIX"}"   # tolerate full session name
    printf '%s' "$arg"; return 0
  fi
  local slugs=() s
  for f in "$XRLIVE_SESSIONS"/*.json; do
    [ -e "$f" ] || continue
    s="$(basename "$f" .json)"
    xr_be_alive "$(xr_slug_ref "$s")" "$(xr_slug_backend "$s")" && slugs+=("$s")
  done
  if [ "${#slugs[@]}" -eq 0 ]; then
    xr_die "no active review session. (start one with /xreview:live, or see /xreview:status)"
  elif [ "${#slugs[@]}" -gt 1 ]; then
    xr_log "multiple active sessions — specify a slug:"
    printf '  %s\n' "${slugs[@]}" >&2
    exit 1
  fi
  printf '%s' "${slugs[0]}"
}

# Read a field from a session's meta.json by slug. Usage: xr_meta <slug> <jq-key>
xr_meta() {
  local slug="$1" key="$2" f="$XRLIVE_SESSIONS/$1.json"
  [ -f "$f" ] || return 1
  jq -r --arg k "$key" '.[$k] // empty' "$f" 2>/dev/null
}

# Single-quote a string for safe embedding in a shell command line.
xr_shq() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}
