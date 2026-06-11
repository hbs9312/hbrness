#!/usr/bin/env bash
# Start a background peer-review: launch the *other* coding agent in a detached
# tmux session to review the current branch's diff, write its review to a file,
# and ping this pane when done.
#
# Usage:
#   start.sh --current-tool <claude|codex> [--reviewer <claude|codex>]
#            [--base <ref>] [--scope branch|working|pr]
#            [--approve auto|manual] [--context <text>] [--title <text>]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

current_tool=""
reviewer=""
base=""
scope="branch"
approve="auto"
context=""
title=""
launch_override="${XRLIVE_LAUNCH_OVERRIDE:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --current-tool) current_tool="$2"; shift 2 ;;
    --reviewer)     reviewer="$2"; shift 2 ;;
    --base)         base="$2"; shift 2 ;;
    --scope)        scope="$2"; shift 2 ;;
    --approve)      approve="$2"; shift 2 ;;
    --context)      context="$2"; shift 2 ;;
    --title)        title="$2"; shift 2 ;;
    --launch-cmd)   launch_override="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,12p' "$SCRIPT_DIR/start.sh"; exit 0 ;;
    -*) xr_die "unknown flag: $1" ;;
    *)  xr_die "unexpected argument: $1" ;;
  esac
done

xr_need git
xr_need jq
xr_need tmux
xr_in_tmux || xr_die "not inside a tmux session — this skill opens the reviewer in a tmux pane/popup. Start tmux first."
xr_init_home

# Resolve tools
[ -n "$current_tool" ] || xr_die "--current-tool is required (claude|codex)"
[ -n "$reviewer" ] || reviewer="$(xr_opposite_tool "$current_tool")"
if [ -z "$launch_override" ]; then
  case "$reviewer" in claude|codex) ;; *) xr_die "unsupported reviewer: $reviewer (claude|codex). For other agents, pass --launch-cmd '<cmd>'.";; esac
  command -v "$reviewer" >/dev/null 2>&1 || xr_die "reviewer CLI not found on PATH: $reviewer"
fi

# Repo context
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || xr_die "not in a git repository"
repo_key="$(xr_repo_key "$REPO_ROOT")"
branch="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
shorthash="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo nohead)"

# Resolve base ref for branch scope
if [ -z "$base" ] && [ "$scope" = "branch" ]; then
  for cand in "$(git -C "$REPO_ROOT" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)" main master develop; do
    [ -n "$cand" ] || continue
    if git -C "$REPO_ROOT" rev-parse --verify -q "$cand" >/dev/null 2>&1; then base="$cand"; break; fi
    if git -C "$REPO_ROOT" rev-parse --verify -q "origin/$cand" >/dev/null 2>&1; then base="origin/$cand"; break; fi
  done
  [ -n "$base" ] || xr_die "could not auto-detect a base branch; pass --base <ref> (or --scope working)"
fi

# Compute the diff + changed-file list per scope
diff_text=""; stat_text=""; files_text=""; scope_desc=""
case "$scope" in
  branch)
    mb="$(git -C "$REPO_ROOT" merge-base "$base" HEAD 2>/dev/null || echo "$base")"
    scope_desc="branch '$branch' vs base '$base' (merge-base $(git -C "$REPO_ROOT" rev-parse --short "$mb" 2>/dev/null || echo "$mb"))"
    stat_text="$(git -C "$REPO_ROOT" diff --stat "$mb"...HEAD)"
    files_text="$(git -C "$REPO_ROOT" diff --name-status "$mb"...HEAD)"
    diff_text="$(git -C "$REPO_ROOT" diff "$mb"...HEAD)"
    ;;
  working)
    scope_desc="uncommitted working-tree changes (tracked, vs HEAD)"
    stat_text="$(git -C "$REPO_ROOT" diff --stat HEAD)"
    files_text="$(git -C "$REPO_ROOT" diff --name-status HEAD)"
    diff_text="$(git -C "$REPO_ROOT" diff HEAD)"
    ;;
  pr)
    command -v gh >/dev/null 2>&1 || xr_die "--scope pr needs the gh CLI"
    scope_desc="open pull request for branch '$branch' (gh pr diff)"
    diff_text="$(gh pr diff 2>/dev/null)" || xr_die "gh pr diff failed — is there an open PR for this branch?"
    stat_text="$(printf '%s\n' "$diff_text" | grep -E '^(diff --git|\+\+\+ |--- )' | head -200 || true)"
    files_text="$(printf '%s\n' "$diff_text" | sed -n 's/^diff --git a\/.* b\///p' || true)"
    ;;
  *) xr_die "unknown scope: $scope (branch|working|pr)" ;;
esac

[ -n "$diff_text" ] || xr_die "no diff to review for scope '$scope'. Nothing changed?"

# Load the code-review preset (sibling skill: skills/review/presets/code.md)
preset_file="$SCRIPT_DIR/../../review/presets/code.md"
preset_body=""
if [ -f "$preset_file" ]; then
  preset_body="$(cat "$preset_file")"
else
  xr_log "code preset not found at $preset_file — proceeding with a minimal perspective"
  preset_body=$'## Review Perspective\n정확성·보안·에러 처리·동시성·성능·계약 일치·유지보수성을 점검하세요.\n\n## Severity Guidance\ncritical / warning / info 로 분류하세요.'
fi

# Slug + work dir
slug="$(xr_sanitize "${branch}-${shorthash}")"
WORK="$XRLIVE_HOME/$repo_key/$slug"
mkdir -p "$WORK"
REQUEST="$WORK/REVIEW_REQUEST.md"
RESULT="$WORK/REVIEW_RESULT.md"
rm -f "$RESULT"   # fresh run
SESS="$(xr_session_name "$slug")"
launcher_pane="$(xr_current_pane || echo '')"
created="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Assemble the review request the reviewer will read
{
  printf '# Code Review Request\n\n- Repository: `%s`\n- Scope: %s\n- Generated: %s by xreview:live (launcher=%s, reviewer=%s)\n\n' \
    "$repo_key" "$scope_desc" "$created" "$current_tool" "$reviewer"
  if [ -n "$context" ]; then
    printf '## Caller Context\n\n%s\n\n---\n\n' "$context"
  fi
  printf '## Default Context\n\n이 변경분은 머지 후보입니다. 동료 엔지니어가 머지 가부를 판단하기 위한 엄격한 리뷰가 필요합니다.\n\n'
  printf '%s\n\n' "$preset_body"
  printf '## Changed Files\n\n```\n%s\n```\n\n' "$files_text"
  printf '## Diff Stat\n\n```\n%s\n```\n\n' "$stat_text"
  printf '## Full Diff\n\n```diff\n%s\n```\n' "$diff_text"
} > "$REQUEST"

# Seed prompt: short, points at the request/result files. READ-ONLY.
seed="You are doing a code review. Read the review request at ${REQUEST} — it has the perspective, severity rules, repo context, and the full diff. This is a READ-ONLY review: do NOT modify any source files. Work through the diff carefully, then write your complete review (findings as file:line + severity + a short rationale each, ordered by severity, ending with a VERDICT: approve / approve-with-nits / request-changes) to ${RESULT}. When ${RESULT} is written, you are done."
if [ -n "$title" ]; then seed="[$title] $seed"; fi

# Build the reviewer launch command.
#  - cwd = WORK (a scratch dir) so the reviewer writes RESULT there.
#  - codex: workspace-write sandbox confines writes to WORK → repo stays read-only.
#  - claude: repo added read-only via --add-dir; acceptEdits auto-accepts the
#    RESULT write so the run is hands-off (read-only enforced by the prompt).
if [ -n "$launch_override" ]; then
  # Advanced/testing seam: run an arbitrary reviewer command (seed appended).
  launch="$launch_override $(xr_shq "$seed")"
else
  case "$reviewer" in
    codex)
      if [ "$approve" = "manual" ]; then
        launch="codex -s workspace-write $(xr_shq "$seed")"
      else
        launch="codex -s workspace-write -a never $(xr_shq "$seed")"
      fi
      ;;
    claude)
      if [ "$approve" = "manual" ]; then
        launch="claude --add-dir $(xr_shq "$REPO_ROOT") $(xr_shq "$seed")"
      else
        launch="claude --add-dir $(xr_shq "$REPO_ROOT") --permission-mode acceptEdits $(xr_shq "$seed")"
      fi
      ;;
  esac
fi

# Launch detached. remain-on-exit keeps the pane (and its scrollback) after the
# agent exits so peek/dock still show the final state; stop.sh tears it down.
tmux new-session -d -s "$SESS" -x 220 -y 50 -c "$WORK" "$launch"
tmux set-option -t "$SESS" remain-on-exit on 2>/dev/null || true
tmux set-option -t "$SESS" window-size manual 2>/dev/null || true

# Background watcher: pings the launcher pane when RESULT appears (or the run ends).
watcher_pid=""
if [ -n "$launcher_pane" ]; then
  nohup bash "$SCRIPT_DIR/notify.sh" "$launcher_pane" "$WORK" "$current_tool" "$slug" \
    >"$WORK/watcher.log" 2>&1 &
  watcher_pid=$!
  disown "$watcher_pid" 2>/dev/null || true
fi

# Persist session metadata (flat index entry).
jq -n \
  --arg slug "$slug" --arg session "$SESS" --arg work "$WORK" \
  --arg request "$REQUEST" --arg result "$RESULT" \
  --arg reviewer "$reviewer" --arg current_tool "$current_tool" \
  --arg repo_key "$repo_key" --arg repo_root "$REPO_ROOT" \
  --arg branch "$branch" --arg base "$base" --arg scope "$scope" \
  --arg launcher_pane "$launcher_pane" --arg watcher_pid "$watcher_pid" \
  --arg created "$created" \
  '{slug:$slug, session:$session, work:$work, request:$request, result:$result,
    reviewer:$reviewer, current_tool:$current_tool, repo_key:$repo_key,
    repo_root:$repo_root, branch:$branch, base:$base, scope:$scope,
    launcher_pane:$launcher_pane, watcher_pid:$watcher_pid, viewport:"",
    created:$created}' > "$XRLIVE_SESSIONS/$slug.json"

cat <<EOF
xreview:live started — reviewer running in the background.
  session : $SESS  (slug: $slug)
  reviewer: $reviewer   scope: $scope_desc
  request : $REQUEST
  result  : $RESULT  (pending — you'll be pinged here when ready)
  peek    : /xreview:live peek        (popup)
  dock    : /xreview:live dock        (split pane)
  status  : /xreview:live status
  stop    : /xreview:live stop
EOF
