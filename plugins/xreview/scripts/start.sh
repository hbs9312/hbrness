#!/usr/bin/env bash
# Start a background peer-review: launch the *other* coding agent in its own
# background session (detached tmux session, or Orca terminal tab) to review the
# current branch's diff, write its review to a file, and ping this pane when done.
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
xr_backend_require
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

# Load the code-review preset (plugin-root: presets/code.md)
preset_file="$SCRIPT_DIR/../presets/code.md"
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
printf 'pending\n' > "$WORK/PING_STATE"
rm -f "$WORK/PING_SENT_AT"
xr_set_watch_state "$WORK" running "리뷰어 기동"   # durable status for pollers
SESS="$(xr_session_name "$slug")"
BACKEND="$(xr_backend)"
launcher_pane="$(xr_launcher_id || echo '')"
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

# The reviewer launches with cwd=WORK (a fresh scratch dir), which would trip
# the harness's workspace-trust dialog. Since the reviewer runs detached and
# can't answer it, pre-accept trust for WORK so the run stays hands-off — for
# whichever reviewer is in play (claude and codex track trust differently).
if [ "$reviewer" = "claude" ] || [ -n "$launch_override" ]; then
  xr_claude_pretrust_dir "$WORK"
  xr_claude_pretrust_dir "$REPO_ROOT"   # claude reviewer adds the repo via --add-dir
fi
if [ "$reviewer" = "codex" ] || [ -n "$launch_override" ]; then
  xr_codex_pretrust_dir "$WORK"
fi

# Wrap the reviewer in a runner script. Two reasons: the launch line carries a
# long quoted seed prompt that would need re-quoting for every backend, and the
# runner records the agent's exit code in RUN_EXIT — the one end-of-run signal
# that works on both backends (Orca leaves the shell alive after the command
# returns, so a live terminal says nothing about the review).
RUNNER="$WORK/run.sh"
rm -f "$WORK/RUN_EXIT"
{
  printf '#!/usr/bin/env bash\n'
  printf 'cd %s || exit 1\n' "$(xr_shq "$WORK")"
  printf '%s\n' "$launch"
  printf 'printf %%s "$?" > %s\n' "$(xr_shq "$WORK/RUN_EXIT")"
  # tmux keeps a finished pane around via remain-on-exit; Orca ends the terminal
  # with its command, which would take the reviewer's scrollback with it. Hold
  # the tab open with a shell so peek still shows how the run ended.
  [ "$BACKEND" = orca ] && printf 'exec "${SHELL:-/bin/bash}" -i\n'
} > "$RUNNER"
chmod +x "$RUNNER"

SESSION_REF="$(xr_be_spawn "$slug" "$WORK" "$REPO_ROOT" "bash $(xr_shq "$RUNNER")")" \
  || xr_die "could not start the reviewer session on backend '$BACKEND'"

watcher_pid=""

# Persist session metadata (flat index entry).
jq -n \
  --arg slug "$slug" --arg session "$SESS" --arg work "$WORK" \
  --arg request "$REQUEST" --arg result "$RESULT" \
  --arg reviewer "$reviewer" --arg current_tool "$current_tool" \
  --arg repo_key "$repo_key" --arg repo_root "$REPO_ROOT" \
  --arg branch "$branch" --arg base "$base" --arg scope "$scope" \
  --arg launcher_pane "$launcher_pane" --arg watcher_pid "$watcher_pid" \
  --arg backend "$BACKEND" --arg session_ref "$SESSION_REF" \
  --arg created "$created" \
  '{slug:$slug, session:$session, work:$work, request:$request, result:$result,
    reviewer:$reviewer, current_tool:$current_tool, repo_key:$repo_key,
    repo_root:$repo_root, branch:$branch, base:$base, scope:$scope,
    backend:$backend, session_ref:$session_ref,
    launcher_pane:$launcher_pane, watcher_pid:$watcher_pid, viewport:"",
    created:$created}' > "$XRLIVE_SESSIONS/$slug.json"


if [ -n "$launcher_pane" ]; then
  if [ "$BACKEND" = "tmux" ]; then
    watcher_session="xwatch-$slug"
    printf -v watcher_command 'env XRLIVE_HOME=%q XRLIVE_BACKEND=tmux bash %q %q %q %q %q >%q 2>&1' \
      "$XRLIVE_HOME" "$SCRIPT_DIR/notify.sh" "$launcher_pane" "$WORK" "$current_tool" "$slug" "$WORK/watcher.log"
    tmux new-session -d -s "$watcher_session" "$watcher_command"
  else
    nohup bash "$SCRIPT_DIR/notify.sh" "$launcher_pane" "$WORK" "$current_tool" "$slug" \
      >"$WORK/watcher.log" 2>&1 &
    watcher_pid=$!
    disown "$watcher_pid" 2>/dev/null || true
    jq --arg pid "$watcher_pid" '.watcher_pid=$pid' "$XRLIVE_SESSIONS/$slug.json" > "$XRLIVE_SESSIONS/$slug.json.tmp"
    mv "$XRLIVE_SESSIONS/$slug.json.tmp" "$XRLIVE_SESSIONS/$slug.json"
  fi
fi

cat <<EOF
xreview:live started — reviewer running in the background.
  session : $SESS  (slug: $slug, backend: $BACKEND)
  reviewer: $reviewer   scope: $scope_desc
  request : $REQUEST
  result  : $RESULT  (pending — you'll be pinged here when ready)
  peek    : /xreview:live peek        (popup)
  dock    : /xreview:live dock        (split pane)
  status  : /xreview:status
  stop    : /xreview:stop
EOF
