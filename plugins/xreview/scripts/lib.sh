#!/usr/bin/env bash
# xreview:live shared library — tmux background-review session helpers.
#
# Storage (Tier 1, namespaced under live/):
#   $XRLIVE_HOME/<repo-key>/<slug>/REVIEW_REQUEST.md
#   $XRLIVE_HOME/<repo-key>/<slug>/REVIEW_RESULT.md
#   $XRLIVE_HOME/<repo-key>/<slug>/meta.json
#   $XRLIVE_HOME/.sessions/<slug>.json     (flat index for status/stop)
#
# A "reviewer" agent runs in a detached tmux session `xrev-<slug>`. The launcher
# (current) pane only sees a completion ping; peek/dock open non-destructive
# viewports (nested `tmux attach`) onto that detached session.
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
# tmux helpers
# ─────────────────────────────────────────────────────────────────────────────

xr_in_tmux() { [ -n "${TMUX:-}" ] || [ -n "${TMUX_PANE:-}" ]; }

xr_current_pane() {
  if [ -n "${TMUX_PANE:-}" ]; then
    printf '%s\n' "$TMUX_PANE"; return 0
  fi
  [ -n "${TMUX:-}" ] || return 1
  tmux display-message -p '#{pane_id}' 2>/dev/null
}

xr_session_name() { printf '%s%s' "$XRLIVE_SESSION_PREFIX" "$1"; }

xr_session_exists() {
  tmux has-session -t "=$1" 2>/dev/null
}

# Echo 1 if the reviewer pane in the session has exited (remain-on-exit), else 0.
xr_session_pane_dead() {
  local sess="$1" out
  out="$(tmux list-panes -t "=$sess" -F '#{pane_dead}' 2>/dev/null | head -1)"
  [ "$out" = "1" ] && printf '1' || printf '0'
}

# Submit a line of text to a pane + Enter. Recipient tool decides submit mode:
# codex needs a CSI-u plain Enter (enhanced keyboard reporting), others plain Enter.
xr_tmux_send_line() {
  local pane="$1" text="$2" recipient_tool="${3:-}"
  text="$(printf '%s' "$text" | tr -d '\r\n')"
  if [ "${#text}" -gt 4000 ]; then text="${text:0:4000}…(truncated)"; fi
  tmux send-keys -t "$pane" -l "$text"
  case "$recipient_tool" in
    codex) tmux send-keys -t "$pane" -l $'\e[13;1u' ;;
    *)     tmux send-keys -t "$pane" Enter ;;
  esac
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
    xr_session_exists "$(xr_session_name "$s")" && slugs+=("$s")
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
