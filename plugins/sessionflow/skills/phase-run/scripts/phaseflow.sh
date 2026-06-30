#!/usr/bin/env bash
# phaseflow.sh — phase-run 엔진 (stage + hook 일반화)
#
# 페이즈로 나뉜 작업을, 각 페이즈 경계에서 컨텍스트를 비우고(/clear) 새 세션이
# HANDOFF.md 를 읽고 다음 페이즈를 이어받도록 자가 주입한다. 모든 tmux/상태 로직은
# 여기에 모여 있고, SKILL.md(LLM)는 이 스크립트를 호출하고 각 페이즈의 "작업" 자체만
# 수행한다.
#
# 핵심 설계:
#   - 주입 대상 pane 은 $TMUX_PANE(이 프로세스 트리에 고정된 pane)을 1순위로 쓴다.
#     tmux display-message 는 "사용자가 현재 보고 있는 pane" 을 주므로, 머신에 여러
#     Claude/Codex 세션이 떠 있으면 엉뚱한 세션에 /clear 를 쏠 수 있다. 절대 금지.
#   - 자동 전진은 detached 프로세스(__inject)가 담당: turn 이 idle 되도록 delay 만큼
#     자고, pause/abort 상태를 재확인한 뒤 clear + continue 키를 보낸다.
#   - 자동 커밋은 절대 하지 않는다. /clear 는 파일을 건드리지 않으므로 워킹트리는
#     그대로 다음 세션이 이어받는다.
#
# 상태 머신 (일반화):
#   - 런(run)은 순서 페이즈 목록을 가진다(phases.tsv: n/status/title).
#   - 각 페이즈는 순서 stage 목록(STAGES, 기본 'work')을 한 turn 안에서 차례로 밟는다.
#     stage = "그 페이즈 안에서 실행할 상태"이며, 각 stage 에 훅을 붙일 수 있다.
#   - 훅은 두 종류:
#       * shell 훅  ($STATE_DIR/hooks/<stage>.shell)  — 엔진이 직접 실행(결정적).
#                    GATES 에 든(또는 GATES=auto 면 shell 훅이 있는 모든) stage 는
#                    "게이트": exit≠0 이면 advance(페이즈 경계 통과)를 거부한다.
#       * prompt 훅 ($STATE_DIR/hooks/<stage>.prompt) — LLM 이 읽어 수행할 지침 텍스트.
#   - /clear 는 stage 마다가 아니라 "페이즈 경계(advance)"에서만 주입된다.
#   - 기본값(STAGES=work, 훅 없음)에서는 기존 phase-run 과 100% 동일하게 동작한다.
#
# 환경변수:
#   PHASEFLOW_DRY_RUN=1   tmux send-keys 를 실제로 쏘지 않고 echo 만 (개발/검증용)
#   HBRNESS_HOME          기본 ~/.hbrness
#   PHASEFLOW_GAP         clear 와 continue 주입 사이 간격(초). 기본 2
#   PHASEFLOW_MAX_PHASES  안전 상한. 기본 50
#   PHASEFLOW_STATE_DIR_NAME  상태 디렉토리명(기본 'phases'). 이 엔진을 다른 워크플로우가
#                         같은 워크트리에서 충돌 없이 재사용할 때 다른 이름을 준다
#                         (예: sessionflow:phase-loop 은 'phase-loop'). HANDOFF.md 경로는
#                         이 디렉토리의 부모(= 워크트리 단위)라 이름과 무관하게 공유된다.

set -euo pipefail

HBRNESS_HOME="${HBRNESS_HOME:-$HOME/.hbrness}"
GAP="${PHASEFLOW_GAP:-2}"
MAX_PHASES="${PHASEFLOW_MAX_PHASES:-50}"
STATE_DIR_NAME="${PHASEFLOW_STATE_DIR_NAME:-phases}"

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

die() { echo "phaseflow: $*" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────────────────────
# 상태 경로 도출 (sessionflow:handoff 와 동일한 워크트리 인지 규약)
# ─────────────────────────────────────────────────────────────────────────────
resolve_state_dir() {
  local git_common git_dir project_root is_worktree wt_name project_key
  git_common=$(git rev-parse --git-common-dir 2>/dev/null || true)
  git_dir=$(git rev-parse --git-dir 2>/dev/null || true)

  if [ -z "$git_common" ]; then
    project_root=$(pwd)
    is_worktree=0
  else
    project_root=$(cd "$(dirname "$git_common")" && pwd)
    if [ "$git_dir" = "$git_common" ]; then
      is_worktree=0
    else
      is_worktree=1
      wt_name=$(basename "$git_dir")
    fi
  fi

  project_key=$(echo "$project_root" | tr '/' '-')

  if [ "$is_worktree" = "1" ]; then
    echo "$HBRNESS_HOME/sessionflow/$project_key/worktrees/$wt_name/$STATE_DIR_NAME"
  else
    echo "$HBRNESS_HOME/sessionflow/$project_key/$STATE_DIR_NAME"
  fi
}

STATE_DIR="$(resolve_state_dir)"
STATE_ENV="$STATE_DIR/state.env"
PHASES_TSV="$STATE_DIR/phases.tsv"
PAUSE_SENTINEL="$STATE_DIR/PAUSED"
HOOKS_DIR="$STATE_DIR/hooks"
GATES_TSV="$STATE_DIR/gates.tsv"
# HANDOFF.md 는 phases/ 의 부모(= sessionflow:handoff 와 동일 경로)에 둔다.
HANDOFF_FILE="$(dirname "$STATE_DIR")/HANDOFF.md"

# ─────────────────────────────────────────────────────────────────────────────
# 상태 read/write
# ─────────────────────────────────────────────────────────────────────────────
load_state() {
  [ -f "$STATE_ENV" ] || die "활성 phase-run 이 없습니다 ($STATE_ENV). 먼저 'init' 하세요."
  # shellcheck disable=SC1090
  . "$STATE_ENV"
  # 구버전 state.env 호환: stage/hook 필드가 없으면 기본값으로 채운다(= 기존 동작).
  STAGES="${STAGES:-work}"
  GATES="${GATES:-auto}"
  STAGE_IDX="${STAGE_IDX:-1}"
}

# base64 helpers (clear_cmd / continue_prompt 에 공백·슬래시가 있어도 안전하게 저장)
b64enc() { printf '%s' "$1" | base64 | tr -d '\n'; }
b64dec() { printf '%s' "$1" | base64 --decode; }

write_state() {
  # 전역 변수 직렬화
  mkdir -p "$STATE_DIR"
  {
    echo "TOOL=$(printf '%q' "$TOOL")"
    echo "PANE=$(printf '%q' "$PANE")"
    echo "CURSOR=$CURSOR"
    echo "TOTAL=$TOTAL"
    echo "STATUS=$(printf '%q' "$STATUS")"
    echo "COMMIT_EACH=$COMMIT_EACH"
    echo "DELAY=$DELAY"
    echo "CLEAR_B64=$(printf '%q' "$CLEAR_B64")"
    echo "CONTINUE_B64=$(printf '%q' "$CONTINUE_B64")"
    echo "CREATED=$(printf '%q' "$CREATED")"
    echo "STAGES=$(printf '%q' "$STAGES")"
    echo "GATES=$(printf '%q' "$GATES")"
    echo "STAGE_IDX=$STAGE_IDX"
  } > "$STATE_ENV"
}

phase_title() { # $1=n
  awk -F'\t' -v n="$1" '$1==n {print $3}' "$PHASES_TSV" 2>/dev/null
}

set_phase_status() { # $1=n  $2=status
  local tmp; tmp="$(mktemp)"
  awk -F'\t' -v n="$1" -v st="$2" 'BEGIN{OFS="\t"} {if($1==n)$2=st; print}' "$PHASES_TSV" > "$tmp"
  mv "$tmp" "$PHASES_TSV"
}

# ─────────────────────────────────────────────────────────────────────────────
# stage / hook 헬퍼
# ─────────────────────────────────────────────────────────────────────────────
# STAGES 는 쉼표 구분 토큰 목록. 토큰명은 [A-Za-z0-9_-] 만 허용(쉼표/공백 금지).
stage_list() { printf '%s' "$STAGES" | tr ',' ' '; }

stage_count() {
  local s n=0
  for s in $(stage_list); do n=$((n+1)); done
  echo "$n"
}

stage_at() { # $1=idx(1-based)
  printf '%s' "$STAGES" | awk -F, -v i="$1" '{print $i}'
}

stage_valid() { # $1=stage  → 0 if in STAGES
  local s
  for s in $(stage_list); do [ "$s" = "$1" ] && return 0; done
  return 1
}

shell_hook_file()  { echo "$HOOKS_DIR/$1.shell"; }
prompt_hook_file() { echo "$HOOKS_DIR/$1.prompt"; }

# stage 가 게이트인가? GATES=auto → shell 훅이 있으면 게이트. 그 외 → GATES 목록에 들면 게이트.
is_gate() { # $1=stage
  local s
  if [ "$GATES" = "auto" ]; then
    [ -f "$(shell_hook_file "$1")" ]
    return $?
  fi
  for s in $(printf '%s' "$GATES" | tr ',' ' '); do
    [ "$s" = "$1" ] && return 0
  done
  return 1
}

# gates.tsv: phase<TAB>stage<TAB>exit  (upsert)
record_gate() { # $1=phase $2=stage $3=exit
  mkdir -p "$STATE_DIR"
  local tmp; tmp="$(mktemp)"
  [ -f "$GATES_TSV" ] && awk -F'\t' -v p="$1" -v s="$2" '!($1==p && $2==s)' "$GATES_TSV" > "$tmp" || true
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$tmp"
  mv "$tmp" "$GATES_TSV"
}

gate_result() { # $1=phase $2=stage  → echo exit code, or empty if 미실행
  [ -f "$GATES_TSV" ] || return 0
  awk -F'\t' -v p="$1" -v s="$2" '$1==p && $2==s {print $3}' "$GATES_TSV" 2>/dev/null
}

clear_gates_for_phase() { # $1=phase
  [ -f "$GATES_TSV" ] || return 0
  local tmp; tmp="$(mktemp)"
  awk -F'\t' -v p="$1" '$1!=p' "$GATES_TSV" > "$tmp" || true
  mv "$tmp" "$GATES_TSV"
}

# ─────────────────────────────────────────────────────────────────────────────
# pane 도출 — $TMUX_PANE 1순위, 폴백은 display-message
# ─────────────────────────────────────────────────────────────────────────────
current_pane() {
  if [ -n "${TMUX_PANE:-}" ]; then
    echo "$TMUX_PANE"
  elif [ -n "${TMUX:-}" ]; then
    tmux display-message -p '#{pane_id}' 2>/dev/null || true
  fi
}

in_tmux() { [ -n "${TMUX:-}" ]; }

# ─────────────────────────────────────────────────────────────────────────────
# tmux 주입 primitives
# ─────────────────────────────────────────────────────────────────────────────
tmux_send_line() { # $1=pane  $2=text
  local pane="$1" text="$2"
  text="$(printf '%s' "$text" | tr -d '\r\n')"
  if [ "${PHASEFLOW_DRY_RUN:-}" = "1" ]; then
    echo "[dry-run] tmux send-keys -t $pane -l '$text'"
  else
    tmux send-keys -t "$pane" -l "$text"
  fi
}

tmux_submit() { # $1=pane  $2=tool
  local pane="$1" tool="$2"
  if [ "$tool" = "codex" ]; then
    # codex TUI(enhanced keyboard reporting): plain Enter 는 Ctrl-M 으로 들어가 줄바꿈됨.
    # CSI-u plain Enter 시퀀스로 제출.
    if [ "${PHASEFLOW_DRY_RUN:-}" = "1" ]; then
      echo "[dry-run] tmux send-keys -t $pane -l <CSI-u Enter>"
    else
      tmux send-keys -t "$pane" -l $'\e[13;1u'
    fi
  else
    if [ "${PHASEFLOW_DRY_RUN:-}" = "1" ]; then
      echo "[dry-run] tmux send-keys -t $pane Enter"
    else
      tmux send-keys -t "$pane" Enter
    fi
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# defaults
# ─────────────────────────────────────────────────────────────────────────────
default_clear_cmd() { # $1=tool
  case "$1" in
    codex) echo "/new" ;;   # ⚠ codex 버전에 따라 다를 수 있음 — --clear-cmd 로 override 가능
    *)     echo "/clear" ;;
  esac
}

# 쉼표 목록 정규화: 공백 제거, 빈 토큰 제거, 토큰 문법 검증.
normalize_stage_list() { # $1=raw → echo normalized, die on bad token
  local raw="$1" out="" tok
  raw="$(printf '%s' "$raw" | tr -d '[:space:]')"
  local IFS=','
  for tok in $raw; do
    [ -z "$tok" ] && continue
    case "$tok" in
      *[!A-Za-z0-9_-]*) die "stage 토큰에 허용되지 않는 문자: '$tok' ([A-Za-z0-9_-] 만 가능)" ;;
    esac
    out="${out:+$out,}$tok"
  done
  echo "$out"
}

# ─────────────────────────────────────────────────────────────────────────────
# subcommands
# ─────────────────────────────────────────────────────────────────────────────
cmd_init() {
  local pane="" tool="claude" commit_each=0 delay=4 clear_cmd="" continue_prompt="/phase-run continue"
  local stages="work" gates="auto"
  while [ $# -gt 0 ]; do
    case "$1" in
      --pane) pane="$2"; shift 2 ;;
      --tool) tool="$2"; shift 2 ;;
      --commit-each) commit_each=1; shift ;;
      --delay) delay="$2"; shift 2 ;;
      --clear-cmd) clear_cmd="$2"; shift 2 ;;
      --continue-prompt) continue_prompt="$2"; shift 2 ;;
      --stages) stages="$2"; shift 2 ;;
      --gates) gates="$2"; shift 2 ;;
      *) die "init: 알 수 없는 인자 $1" ;;
    esac
  done
  [ -n "$pane" ] || pane="$(current_pane)"
  [ -n "$clear_cmd" ] || clear_cmd="$(default_clear_cmd "$tool")"

  stages="$(normalize_stage_list "$stages")"
  [ -n "$stages" ] || stages="work"
  if [ "$gates" != "auto" ]; then
    gates="$(normalize_stage_list "$gates")"
  fi

  # 페이즈 제목을 stdin 에서 (한 줄당 하나)
  mkdir -p "$STATE_DIR"
  : > "$PHASES_TSV"
  : > "$GATES_TSV"
  local n=0 line
  while IFS= read -r line || [ -n "$line" ]; do
    line="$(printf '%s' "$line" | tr -d '\r' | sed 's/\t/ /g')"
    [ -z "${line// }" ] && continue
    n=$((n+1))
    [ "$n" -le "$MAX_PHASES" ] || die "페이즈 수가 상한($MAX_PHASES)을 초과했습니다."
    local st="pending"; [ "$n" = "1" ] && st="active"
    printf '%s\t%s\t%s\n' "$n" "$st" "$line" >> "$PHASES_TSV"
  done
  [ "$n" -ge 1 ] || die "페이즈 제목을 stdin 으로 한 줄에 하나씩 주세요."

  TOOL="$tool"; PANE="$pane"; CURSOR=1; TOTAL="$n"; STATUS="active"
  COMMIT_EACH="$commit_each"; DELAY="$delay"
  CLEAR_B64="$(b64enc "$clear_cmd")"; CONTINUE_B64="$(b64enc "$continue_prompt")"
  CREATED="$(date '+%Y-%m-%d %H:%M:%S')"
  STAGES="$stages"; GATES="$gates"; STAGE_IDX=1
  write_state
  rm -f "$PAUSE_SENTINEL"

  echo "phase-run 시작: 총 ${TOTAL}개 페이즈, 현재 → Phase 1"
  echo "  tool=$TOOL  pane=${PANE:-<none>}  delay=${DELAY}s  commit-each=$COMMIT_EACH  clear='${clear_cmd}'"
  echo "  stages=$STAGES  gates=$GATES"
  echo "  state: $STATE_DIR"
  if ! in_tmux; then
    echo "  ⚠ tmux 밖이라 자동 전진 불가 — 경계마다 수동으로 '$clear_cmd' 후 '$continue_prompt' 실행 필요."
  fi
  cmd_status
}

# set-hook <stage> --shell|--prompt   (본문은 stdin)
cmd_set_hook() {
  local stage="" kind=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --shell)  kind="shell"; shift ;;
      --prompt) kind="prompt"; shift ;;
      -*) die "set-hook: 알 수 없는 인자 $1" ;;
      *) [ -z "$stage" ] && stage="$1" || die "set-hook: 인자 과다 ($1)"; shift ;;
    esac
  done
  [ -n "$stage" ] || die "set-hook: <stage> 필요"
  [ -n "$kind" ]  || die "set-hook: --shell 또는 --prompt 필요"
  load_state
  stage_valid "$stage" || die "set-hook: '$stage' 는 STAGES($STAGES) 에 없는 stage 입니다."
  mkdir -p "$HOOKS_DIR"
  local f
  [ "$kind" = "shell" ] && f="$(shell_hook_file "$stage")" || f="$(prompt_hook_file "$stage")"
  cat > "$f"
  echo "✓ hook 등록: $kind[$stage] → $f"
  is_gate "$stage" && echo "  ('$stage' 는 게이트 — 이 stage 의 shell 훅이 통과해야 advance 가능)"
}

cmd_status() {
  [ -f "$STATE_ENV" ] || { echo "활성 phase-run 없음."; return 0; }
  load_state
  echo "── phase-run 상태 ──────────────────────────────"
  echo "상태: $STATUS   진행: $CURSOR/$TOTAL   tool=$TOOL  pane=${PANE:-<none>}"
  echo "stages: $STAGES   (현재 stage → $(stage_at "$STAGE_IDX"))"
  [ -f "$PAUSE_SENTINEL" ] && echo "⏸  PAUSED (resume 으로 재개)"
  local n stt ttl
  while IFS=$'\t' read -r n stt ttl; do
    local mark="  "
    case "$stt" in
      done)    mark="✓ " ;;
      active)  mark="▶ " ;;
      pending) mark="· " ;;
    esac
    printf '  %sPhase %s  %s\n' "$mark" "$n" "$ttl"
  done < "$PHASES_TSV"
  # 현재 페이즈의 stage/게이트 상태
  local s g r
  echo "  ── 현재 페이즈 stage ──"
  for s in $(stage_list); do
    g=""; is_gate "$s" && g=" [gate]"
    r="$(gate_result "$CURSOR" "$s")"
    local rmark="·"
    [ -n "$r" ] && { [ "$r" = "0" ] && rmark="✓" || rmark="✗($r)"; }
    printf '    %s %s%s\n' "$rmark" "$s" "$g"
  done
  echo "────────────────────────────────────────────────"
}

cmd_current() {
  load_state
  # LLM 이 "지금 무슨 페이즈/stage 를 해야 하는지" 파싱하기 쉬운 형태
  echo "STATUS=$STATUS"
  echo "CURSOR=$CURSOR"
  echo "TOTAL=$TOTAL"
  echo "COMMIT_EACH=$COMMIT_EACH"
  echo "TITLE=$(phase_title "$CURSOR")"
  echo "HANDOFF=$HANDOFF_FILE"
  echo "STAGES=$STAGES"
  echo "STAGE_IDX=$STAGE_IDX"
  echo "STAGE=$(stage_at "$STAGE_IDX")"
}

# stage — 현재 stage 의 훅 정보를 LLM 파싱용으로 출력
cmd_stage() {
  load_state
  local s; s="$(stage_at "$STAGE_IDX")"
  echo "STAGE=$s"
  echo "STAGE_IDX=$STAGE_IDX"
  echo "STAGE_COUNT=$(stage_count)"
  is_gate "$s" && echo "GATE=1" || echo "GATE=0"
  [ -f "$(shell_hook_file "$s")" ]  && echo "HAS_SHELL=1"  || echo "HAS_SHELL=0"
  [ -f "$(prompt_hook_file "$s")" ] && echo "HAS_PROMPT=1" || echo "HAS_PROMPT=0"
}

# run-hooks <stage> [--no-gate] — 그 stage 의 prompt 훅을 출력하고 shell 훅을 실행.
# shell 훅의 exit code 를 그대로 반환하고 gates.tsv 에 기록한다.
cmd_run_hooks() {
  local stage="" no_gate=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --no-gate) no_gate=1; shift ;;
      -*) die "run-hooks: 알 수 없는 인자 $1" ;;
      *) [ -z "$stage" ] && stage="$1" || die "run-hooks: 인자 과다 ($1)"; shift ;;
    esac
  done
  [ -n "$stage" ] || die "run-hooks: <stage> 필요"
  load_state
  stage_valid "$stage" || die "run-hooks: '$stage' 는 STAGES($STAGES) 에 없는 stage 입니다."

  local pf sf
  pf="$(prompt_hook_file "$stage")"
  if [ -f "$pf" ]; then
    echo "──PROMPT[$stage]────────────────────────────────"
    cat "$pf"
    echo ""
    echo "────────────────────────────────────────────────"
  fi

  sf="$(shell_hook_file "$stage")"
  if [ ! -f "$sf" ]; then
    # shell 훅 없음 → 게이트 통과로 간주(기록).
    record_gate "$CURSOR" "$stage" 0
    [ -f "$pf" ] || echo "ℹ stage '$stage' 에 훅 없음 (no-op)."
    return 0
  fi

  echo "▶ run-hooks[$stage] (Phase $CURSOR) — shell 훅 실행:"
  echo "  \$ $(head -1 "$sf")$([ "$(wc -l <"$sf")" -gt 1 ] && echo ' …')"
  local code=0
  set +e
  ( cd "$(pwd)" && bash "$sf" )
  code=$?
  set -e
  record_gate "$CURSOR" "$stage" "$code"

  if [ "$code" -eq 0 ]; then
    echo "✓ hook 통과[$stage]"
  else
    if [ "$no_gate" = "1" ] || ! is_gate "$stage"; then
      echo "⚠ hook 실패[$stage] (code=$code) — 게이트 아님/무시. advance 는 막지 않음."
    else
      echo "✗ 게이트 실패[$stage] (code=$code) — 수정 후 'run-hooks $stage' 재실행해야 advance 가능."
    fi
  fi
  return "$code"
}

# next-stage — 현재 페이즈 안에서 stage 커서를 한 칸 전진.
# 더 진행할 stage 가 있으면 다음 stage 를, 다 소진했으면 PHASE_COMPLETE 를 출력.
cmd_next_stage() {
  load_state
  local cnt; cnt="$(stage_count)"
  if [ "$STAGE_IDX" -lt "$cnt" ]; then
    STAGE_IDX=$((STAGE_IDX+1))
    write_state
    echo "STAGE_IDX=$STAGE_IDX"
    echo "STAGE=$(stage_at "$STAGE_IDX")"
  else
    echo "PHASE_COMPLETE=1"
    echo "ℹ 이 페이즈의 모든 stage 완료 — 'advance' 로 페이즈 경계를 넘으세요."
  fi
}

# advance 의 게이트 검사 — 현재 페이즈의 모든 게이트 stage 가 exit 0 인지 확인.
check_gates() { # → 0 ok, 아니면 die
  local s r missing="" failed=""
  for s in $(stage_list); do
    is_gate "$s" || continue
    r="$(gate_result "$CURSOR" "$s")"
    if [ -z "$r" ]; then
      missing="${missing:+$missing }$s"
    elif [ "$r" != "0" ]; then
      failed="${failed:+$failed }$s($r)"
    fi
  done
  if [ -n "$failed" ]; then
    die "advance 거부: 게이트 실패 → $failed. 수정 후 재실행하거나 'advance --force'."
  fi
  if [ -n "$missing" ]; then
    die "advance 거부: 미실행 게이트 → $missing. 'run-hooks <stage>' 먼저 실행하거나 'advance --force'."
  fi
}

# detached injector 를 예약
schedule_inject() {
  load_state
  if ! in_tmux || [ -z "${PANE:-}" ]; then
    return 1
  fi
  if [ "${PHASEFLOW_DRY_RUN:-}" = "1" ]; then
    # 드라이런: detach 하지 않고 즉시 동기 실행(검증용)
    "$SELF" __inject --immediate
    return 0
  fi
  nohup bash "$SELF" __inject >/dev/null 2>&1 &
  disown 2>/dev/null || true
  return 0
}

cmd_advance() {
  local pane="" tool="" force=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --pane) pane="$2"; shift 2 ;;
      --tool) tool="$2"; shift 2 ;;
      --force) force=1; shift ;;
      *) die "advance: 알 수 없는 인자 $1" ;;
    esac
  done
  load_state
  [ "$STATUS" = "active" ] || die "advance 불가: 상태가 '$STATUS' 입니다."

  # 게이트 검사 (--force 면 건너뜀)
  if [ "$force" != "1" ]; then
    check_gates
  fi

  # pane/tool 을 호출 시점 값으로 갱신(세션마다 재캡처가 가장 안전)
  [ -n "$pane" ] && PANE="$pane"
  [ -n "$tool" ] && TOOL="$tool"

  set_phase_status "$CURSOR" "done"
  clear_gates_for_phase "$CURSOR"
  CURSOR=$((CURSOR+1))
  STAGE_IDX=1

  if [ "$CURSOR" -gt "$TOTAL" ]; then
    STATUS="done"
    write_state
    echo "✅ 모든 페이즈 완료 ($TOTAL/$TOTAL). phase-run 종료."
    echo "   상태 파일은 'reset' 으로 정리할 수 있습니다."
    return 0
  fi

  set_phase_status "$CURSOR" "active"
  write_state

  local clear_cmd continue_prompt
  clear_cmd="$(b64dec "$CLEAR_B64")"
  continue_prompt="$(b64dec "$CONTINUE_B64")"

  # 제어 커맨드 접두어를 continue_prompt 에서 도출 (예: '/phase-loop continue' → '/phase-loop')
  local ctl_cmd; ctl_cmd="$(printf '%s' "$continue_prompt" | awk '{print $1}')"
  [ -n "$ctl_cmd" ] || ctl_cmd="/phase-run"

  echo "Phase $((CURSOR-1)) 완료 → Phase $CURSOR ($(phase_title "$CURSOR")) 준비."
  if schedule_inject; then
    echo "⏳ ${DELAY}s 후 자동으로 '$clear_cmd' → '$continue_prompt' (pane=$PANE)."
    echo "   중단하려면 즉시 '$ctl_cmd pause' 실행."
  else
    echo "⚠ tmux 자동 전진 불가. 이 세션에서 직접 실행하세요:"
    echo "     $clear_cmd"
    echo "     $continue_prompt"
  fi
}

cmd_pause() {
  load_state
  STATUS="paused"; write_state
  : > "$PAUSE_SENTINEL"
  echo "⏸ phase-run 일시정지. 예약된 자동 전진은 취소됩니다. 'resume' 으로 재개."
}

cmd_resume() {
  load_state
  rm -f "$PAUSE_SENTINEL"
  STATUS="active"; write_state
  echo "▶ 재개. Phase $CURSOR ($(phase_title "$CURSOR")) 로 전진합니다."
  local clear_cmd continue_prompt
  clear_cmd="$(b64dec "$CLEAR_B64")"; continue_prompt="$(b64dec "$CONTINUE_B64")"
  if schedule_inject; then
    echo "⏳ ${DELAY}s 후 '$clear_cmd' → '$continue_prompt' (pane=$PANE)."
  else
    echo "⚠ 수동 실행 필요: $clear_cmd  그리고  $continue_prompt"
  fi
}

cmd_stop() {
  load_state
  STATUS="aborted"; write_state
  rm -f "$PAUSE_SENTINEL"
  echo "⏹ phase-run 중단(aborted). 상태는 보존됩니다('status' 로 확인, 'reset' 으로 삭제)."
}

cmd_reset() {
  rm -rf "$STATE_DIR"
  echo "🧹 phase-run 상태 삭제: $STATE_DIR"
}

cmd_paths() {
  echo "STATE_DIR=$STATE_DIR"
  echo "STATE_ENV=$STATE_ENV"
  echo "PHASES_TSV=$PHASES_TSV"
  echo "GATES_TSV=$GATES_TSV"
  echo "HOOKS_DIR=$HOOKS_DIR"
  echo "PAUSE_SENTINEL=$PAUSE_SENTINEL"
  echo "HANDOFF_FILE=$HANDOFF_FILE"
  echo "TMUX_PANE=${TMUX_PANE:-}"
  echo "current_pane=$(current_pane)"
}

# detached 로 도는 실제 주입기
cmd___inject() {
  local immediate=0
  [ "${1:-}" = "--immediate" ] && immediate=1
  load_state

  if [ "$immediate" != "1" ]; then
    sleep "$DELAY"
  fi

  # fire 직전 재확인 — pause/abort 되었거나 상태가 바뀌었으면 중단
  load_state
  if [ -f "$PAUSE_SENTINEL" ] || [ "$STATUS" != "active" ]; then
    exit 0
  fi
  [ -n "${PANE:-}" ] || exit 0
  [ "$CURSOR" -ge 1 ] && [ "$CURSOR" -le "$TOTAL" ] || exit 0

  local clear_cmd continue_prompt
  clear_cmd="$(b64dec "$CLEAR_B64")"
  continue_prompt="$(b64dec "$CONTINUE_B64")"

  tmux_send_line "$PANE" "$clear_cmd"
  tmux_submit    "$PANE" "$TOOL"
  if [ "${PHASEFLOW_DRY_RUN:-}" = "1" ]; then
    echo "[dry-run] sleep $GAP"
  else
    sleep "$GAP"
  fi
  tmux_send_line "$PANE" "$continue_prompt"
  tmux_submit    "$PANE" "$TOOL"
}

# ─────────────────────────────────────────────────────────────────────────────
main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    init)       cmd_init "$@" ;;
    set-hook)   cmd_set_hook "$@" ;;
    status)     cmd_status ;;
    current)    cmd_current ;;
    stage)      cmd_stage ;;
    run-hooks)  cmd_run_hooks "$@" ;;
    next-stage) cmd_next_stage ;;
    advance)    cmd_advance "$@" ;;
    pause)      cmd_pause ;;
    resume)     cmd_resume ;;
    stop|abort) cmd_stop ;;
    reset)      cmd_reset ;;
    paths)      cmd_paths ;;
    __inject)   cmd___inject "$@" ;;
    ""|-h|--help)
      cat <<'USAGE'
phaseflow.sh <subcommand>
  init --pane <id> --tool <claude|codex> [--commit-each] [--delay N] [--clear-cmd C]
       [--continue-prompt P] [--stages a,b,c] [--gates a,b|auto]   (페이즈 제목 stdin, 한 줄당 하나)
  set-hook <stage> --shell|--prompt        그 stage 의 훅 본문을 stdin 으로 등록
  status                현재 페이즈/ stage / 게이트 상태 표시
  current               LLM 파싱용 현재 커서/제목/ stage (KEY=VALUE)
  stage                 현재 stage 의 훅/게이트 정보 (KEY=VALUE)
  run-hooks <stage> [--no-gate]   그 stage 의 prompt 훅 출력 + shell 훅 실행(게이트 기록)
  next-stage            현재 페이즈 안에서 stage 커서 전진(소진 시 PHASE_COMPLETE)
  advance [--pane id] [--tool t] [--force]   현재 페이즈 done, 게이트 확인 후 전진 + clear/continue 예약
  pause | resume | stop | reset    제어
  paths                 디버그: 경로/ pane 도출 확인
USAGE
      ;;
    *) die "알 수 없는 subcommand: $sub (--help 참고)" ;;
  esac
}

main "$@"
