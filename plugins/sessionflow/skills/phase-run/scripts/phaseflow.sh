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
#   - Codex: 입력 감시 PTY + 예약 worker가 idle/전환/접수를 확인한다.
#     다른 런타임: 기존 DELAY/GAP + native Enter 경로(__inject)를 유지한다.
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
#   - 기본값(STAGES=work, 훅 없음)은 기존 페이즈/stage 의미를 유지한다.
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
  RUN_ID="${RUN_ID:-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')}"
  STAGES="${STAGES:-work}"
  GATES="${GATES:-auto}"
  STAGE_IDX="${STAGE_IDX:-1}"
}

# base64 helpers (clear_cmd / continue_prompt 에 공백·슬래시가 있어도 안전하게 저장)
b64enc() { printf '%s' "$1" | base64 | tr -d '\n'; }
b64dec() { printf '%s' "$1" | base64 --decode; }

continuation_prompt() {
  local prompt; prompt="$(b64dec "$CONTINUE_B64")"
  if [ "$TOOL" = codex ]; then
    case "$prompt" in
      '/phase-loop '*|'/phase-run '*) prompt="\$${prompt#/}" ;;
      '/sessionflow:phase-loop '*|'/sessionflow:phase-run '*) prompt="\$${prompt#/sessionflow:}" ;;
    esac
  fi
  printf '%s' "$prompt"
}

write_state() {
  # 전역 변수 직렬화
  mkdir -p "$STATE_DIR"
  {
    echo "RUN_ID=$(printf '%q' "$RUN_ID")"
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
  } > "$STATE_ENV.tmp"
  mv "$STATE_ENV.tmp" "$STATE_ENV"
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

# 훅 파일 경로 — 글로벌(쓰기 기본) / 페이즈 스코프
shell_hook_file()  { echo "$HOOKS_DIR/${2:+$2.}$1.shell"; }   # $1=stage [$2=phase]
prompt_hook_file() { echo "$HOOKS_DIR/${2:+$2.}$1.prompt"; }  # $1=stage [$2=phase]

# 읽기용 해석 — 현재 페이즈($CURSOR) override 가 있으면 그것을, 없으면 글로벌을. 둘 다 없으면 빈 문자열.
resolve_hook() { # $1=stage $2=kind(shell|prompt) → 존재하는 경로 or ""
  local p="$HOOKS_DIR/${CURSOR}.$1.$2" g="$HOOKS_DIR/$1.$2"
  if [ -f "$p" ]; then echo "$p"; elif [ -f "$g" ]; then echo "$g"; fi
}

# stage 가 (현재 페이즈 기준) 게이트인가? GATES=auto → shell 훅이 해석되면 게이트. 그 외 → GATES 목록.
is_gate() { # $1=stage
  local s
  if [ "$GATES" = "auto" ]; then
    [ -n "$(resolve_hook "$1" shell)" ]
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
# pane 도출 — 명시된 $TMUX_PANE만; 다른 사용자의 현재 pane으로 폴백하지 않는다
# ─────────────────────────────────────────────────────────────────────────────
current_pane() {
  if [ -n "${TMUX_PANE:-}" ]; then
    echo "$TMUX_PANE"
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

tmux_submit() { # $1=pane $2=tool; Codex must use the guarded adapter.
  [ "$2" != "codex" ] || die "Codex requires codex-guard.py; raw submit disabled"
  # devin/grok 은 직전에 쏟아진 텍스트 버스트와 같은 배치로 들어온 Enter 를
  # 붙여넣기 일부로 삼켜 버린다 — 텍스트와 submit 사이를 잠깐 띄운다.
  case "$2" in devin|grok) sleep "${PHASEFLOW_SUBMIT_DELAY:-1}" ;; esac
  if [ "${PHASEFLOW_DRY_RUN:-}" = "1" ]; then
    echo "[dry-run] tmux send-keys -t $1 Enter"
  else
    tmux send-keys -t "$1" Enter
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# defaults
# ─────────────────────────────────────────────────────────────────────────────
default_clear_cmd() { # $1=tool
  case "$1" in
    codex|grok|devin) echo "/new" ;;
    claude) echo "/clear" ;;
    *) die "unsupported tool: $1 (claude|codex|grok|devin)" ;;
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
  local stages="work" gates="auto" continue_explicit=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --pane) pane="$2"; shift 2 ;;
      --tool) tool="$2"; shift 2 ;;
      --commit-each) commit_each=1; shift ;;
      --delay) delay="$2"; shift 2 ;;
      --clear-cmd) clear_cmd="$2"; shift 2 ;;
      --continue-prompt) continue_prompt="$2"; continue_explicit=1; shift 2 ;;
      --stages) stages="$2"; shift 2 ;;
      --gates) gates="$2"; shift 2 ;;
      *) die "init: 알 수 없는 인자 $1" ;;
    esac
  done
  case "$tool" in claude|codex|grok|devin) ;; *) die "unsupported tool: $tool" ;; esac
  if [ "$continue_explicit" -eq 0 ] && { [ "$tool" = grok ] || [ "$tool" = devin ]; }; then
    continue_prompt="/sessionflow:phase-run continue"
  fi
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
  RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
  CREATED="$(date '+%Y-%m-%d %H:%M:%S')"
  STAGES="$stages"; GATES="$gates"; STAGE_IDX=1
  write_state
  rm -f "$PAUSE_SENTINEL" "$STATE_DIR/inject-ticket.json" "$STATE_DIR/legacy-ticket" "$STATE_DIR/RECOVERY.md"

  echo "phase-run 시작: 총 ${TOTAL}개 페이즈, 현재 → Phase 1"
  echo "  tool=$TOOL  pane=${PANE:-<none>}  delay=${DELAY}s  commit-each=$COMMIT_EACH  clear='${clear_cmd}'"
  echo "  stages=$STAGES  gates=$GATES"
  echo "  state: $STATE_DIR"
  if ! in_tmux; then
    echo "  ⚠ tmux 밖이라 자동 전진 불가 — 경계마다 수동으로 '$clear_cmd' 후 '$continue_prompt' 실행 필요."
  fi
  cmd_status
}

# set-hook <stage> --shell|--prompt [--phase N]   (본문은 stdin)
cmd_set_hook() {
  local stage="" kind="" phase=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --shell)  kind="shell"; shift ;;
      --prompt) kind="prompt"; shift ;;
      --phase)  phase="$2"; shift 2 ;;
      -*) die "set-hook: 알 수 없는 인자 $1" ;;
      *) [ -z "$stage" ] && stage="$1" || die "set-hook: 인자 과다 ($1)"; shift ;;
    esac
  done
  [ -n "$stage" ] || die "set-hook: <stage> 필요"
  [ -n "$kind" ]  || die "set-hook: --shell 또는 --prompt 필요"
  [ -z "$phase" ] || case "$phase" in *[!0-9]*|'') die "set-hook: --phase 는 정수" ;; esac
  load_state
  stage_valid "$stage" || die "set-hook: '$stage' 는 STAGES($STAGES) 에 없는 stage 입니다."
  mkdir -p "$HOOKS_DIR"
  local f
  [ "$kind" = "shell" ] && f="$(shell_hook_file "$stage" "$phase")" || f="$(prompt_hook_file "$stage" "$phase")"
  cat > "$f"
  echo "✓ hook 등록: $kind[$stage]${phase:+ @phase$phase} → $f"
}

# 선언적 훅 스펙(hooks.spec) 경로 — PHASES.md / HANDOFF.md 와 같은 디렉토리.
default_spec_file() { echo "$(dirname "$STATE_DIR")/hooks.spec"; }

# load-hooks [<file>] — 선언 스펙을 파싱해 STAGES/GATES 갱신 + 훅 스토어를 재구성한다.
#
# 스펙 문법(라인 단위):
#   # 주석
#   stages: work, verify, ship          (선택 — STAGES 재정의)
#   gates:  verify, ship | auto          (선택 — GATES 재정의)
#   [verify].shell                       글로벌 shell 훅 블록 시작
#   npm run typecheck
#   [end]                                블록 끝(정확히 '[end]')
#   [verify@2].prompt                    Phase 2 전용 override 블록
#   …
#   [end]
#
# 원자성: 임시 staging 에 쓰고 전부 검증한 뒤에만 기존 hooks/ 를 교체한다.
cmd_load_hooks() {
  local file=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -*) die "load-hooks: 알 수 없는 인자 $1" ;;
      *) [ -z "$file" ] && file="$1" || die "load-hooks: 인자 과다 ($1)"; shift ;;
    esac
  done
  load_state
  [ -n "$file" ] || file="$(default_spec_file)"
  [ -f "$file" ] || die "load-hooks: 스펙 파일 없음: $file"

  local stage_dir; stage_dir="$(mktemp -d)"
  trap "rm -rf '$stage_dir'" EXIT   # 경로를 즉시 전개(local 변수가 EXIT 시점엔 out-of-scope)
  mkdir -p "$stage_dir/hooks"

  local eff_stages="$STAGES" eff_gates="$GATES"
  local seen_stages=""        # 검증용: 스펙에 등장한 stage 토큰들
  local in_block=0 body_file="" lineno=0 line

  while IFS= read -r line || [ -n "$line" ]; do
    lineno=$((lineno+1))
    line="${line%$'\r'}"
    if [ "$in_block" = "1" ]; then
      if [ "$line" = "[end]" ]; then in_block=0; body_file=""; continue; fi
      printf '%s\n' "$line" >> "$body_file"
      continue
    fi
    case "$line" in
      ''|'#'*) continue ;;
    esac
    # 헤더: stages: / gates:
    if [[ "$line" =~ ^stages:[[:space:]]*(.+)$ ]]; then
      eff_stages="$(normalize_stage_list "${BASH_REMATCH[1]}")"
      continue
    fi
    if [[ "$line" =~ ^gates:[[:space:]]*(.+)$ ]]; then
      local gv; gv="$(printf '%s' "${BASH_REMATCH[1]}" | tr -d '[:space:]')"
      [ "$gv" = "auto" ] && eff_gates="auto" || eff_gates="$(normalize_stage_list "$gv")"
      continue
    fi
    # 블록 헤더: [stage].kind  또는 [stage@N].kind
    if [[ "$line" =~ ^\[([A-Za-z0-9_-]+)(@([0-9]+))?\]\.(shell|prompt)$ ]]; then
      local st="${BASH_REMATCH[1]}" ph="${BASH_REMATCH[3]}" kd="${BASH_REMATCH[4]}"
      seen_stages="${seen_stages} ${st}"
      if [ -n "$ph" ]; then body_file="$stage_dir/hooks/${ph}.${st}.${kd}"; else body_file="$stage_dir/hooks/${st}.${kd}"; fi
      : > "$body_file"
      in_block=1
      continue
    fi
    die "load-hooks: 파싱 오류 (line $lineno): '$line'"
  done < "$file"
  [ "$in_block" = "0" ] || die "load-hooks: 닫히지 않은 블록 ('[end]' 누락)."

  [ -n "$eff_stages" ] || eff_stages="work"

  # 검증: 스펙에 등장한 모든 stage 가 최종 STAGES 에 있어야 한다.
  local st
  for st in $seen_stages; do
    printf '%s' "$eff_stages" | tr ',' '\n' | grep -qx "$st" \
      || die "load-hooks: '$st' 는 stages($eff_stages) 에 없는 stage 입니다."
  done
  # gates 가 auto 가 아니면 그 토큰들도 STAGES 에 있어야 한다.
  if [ "$eff_gates" != "auto" ]; then
    for st in $(printf '%s' "$eff_gates" | tr ',' ' '); do
      printf '%s' "$eff_stages" | tr ',' '\n' | grep -qx "$st" \
        || die "load-hooks: gates 의 '$st' 가 stages($eff_stages) 에 없습니다."
    done
  fi

  # 검증 통과 → 원자적 교체.
  rm -rf "$HOOKS_DIR"
  mkdir -p "$HOOKS_DIR"
  if [ -n "$(ls -A "$stage_dir/hooks" 2>/dev/null)" ]; then
    mv "$stage_dir/hooks"/* "$HOOKS_DIR"/
  fi
  STAGES="$eff_stages"; GATES="$eff_gates"; STAGE_IDX=1
  write_state

  echo "✓ load-hooks: $file"
  echo "  stages=$STAGES  gates=$GATES  (STAGE_IDX 1 로 리셋)"
  local f cnt=0
  for f in "$HOOKS_DIR"/*; do [ -e "$f" ] && { echo "  · $(basename "$f")"; cnt=$((cnt+1)); }; done
  echo "  훅 $cnt 개 등록됨."
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
  [ -n "$(resolve_hook "$s" shell)" ]  && echo "HAS_SHELL=1"  || echo "HAS_SHELL=0"
  [ -n "$(resolve_hook "$s" prompt)" ] && echo "HAS_PROMPT=1" || echo "HAS_PROMPT=0"
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
  pf="$(resolve_hook "$stage" prompt)"
  if [ -n "$pf" ]; then
    echo "──PROMPT[$stage]────────────────────────────────"
    cat "$pf"
    echo ""
    echo "────────────────────────────────────────────────"
  fi

  sf="$(resolve_hook "$stage" shell)"
  if [ -z "$sf" ]; then
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
  local inject_command ticket
  if [ "${PHASEFLOW_DRY_RUN:-}" = "1" ]; then
    echo "[dry-run] reservation only; no worker/keys, readiness/transition/acceptance NOT verified."
    return 0
  fi
  if [ "$TOOL" = "codex" ]; then
    ticket=$(python3 "$(dirname "$SELF")/inject.py" prepare "$STATE_DIR") || return 1
    printf -v inject_command 'cd %q && python3 %q worker %q %q >>%q 2>&1' \
      "$(pwd)" "$(dirname "$SELF")/inject.py" "$STATE_DIR" "$ticket" "$STATE_DIR/inject-worker.log"
  else
    # Preserve the native /clear or /new + plain Enter path for other runtimes.
    ticket="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
    printf '%s' "$ticket" > "$STATE_DIR/legacy-ticket"
    local target_identity
    target_identity=$(tmux display-message -p -t "$PANE" '#{pid}|#{pane_id}|#{pane_pid}|#{pane_current_command}') || return 1
    printf -v inject_command 'cd %q && env HBRNESS_HOME=%q PHASEFLOW_STATE_DIR_NAME=%q PHASEFLOW_GAP=%q PHASEFLOW_LOCK_HELD=0 bash %q __inject %q %q %q %q >>%q 2>&1' \
      "$(pwd)" "$HBRNESS_HOME" "$STATE_DIR_NAME" "$GAP" "$SELF" "$RUN_ID" "$CURSOR" "$ticket" "$target_identity" "$STATE_DIR/inject.log"
  fi
  tmux run-shell -b "$inject_command"
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
  continue_prompt="$(continuation_prompt)"

  # 제어 커맨드 접두어를 continue_prompt 에서 도출 (예: '/phase-loop continue' → '/phase-loop')
  local ctl_cmd; ctl_cmd="$(printf '%s' "$continue_prompt" | awk '{print $1}')"
  [ -n "$ctl_cmd" ] || ctl_cmd="/phase-run"

  echo "Phase $((CURSOR-1)) 완료 → Phase $CURSOR ($(phase_title "$CURSOR")) 준비."
  if schedule_inject; then
    echo "⏳ 입력 가능 상태 확인 후 자동 재개 예약 (비-Codex delay=${DELAY}s): '$clear_cmd' → '$continue_prompt' (pane=$PANE)."
    echo "   중단하려면 즉시 '$ctl_cmd pause' 실행."
  else
    echo "⚠ tmux 자동 전진 불가. 이 세션에서 직접 실행하세요:"
    echo "     $clear_cmd"
    echo "     $continue_prompt"
  fi
}

cmd_pause() {
  load_state
  rm -f "$STATE_DIR/inject-ticket.json" "$STATE_DIR/legacy-ticket"
  STATUS="paused"; write_state
  : > "$PAUSE_SENTINEL"
  echo "⏸ phase-run 일시정지. 예약된 자동 전진은 취소됩니다. 'resume' 으로 재개."
}

cmd_resume() {
  local manual=0 pane=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --manual) manual=1; shift ;;
      --pane) pane="$2"; shift 2 ;;
      *) die "resume: 알 수 없는 인자 $1" ;;
    esac
  done
  load_state
  case "$STATUS" in active|paused) ;; *) die "resume 불가: $STATUS (새 init 필요)" ;; esac
  [ -n "$pane" ] && PANE="$pane"
  rm -f "$PAUSE_SENTINEL"
  STATUS="active"; write_state
  echo "▶ 현재 Phase $CURSOR ($(phase_title "$CURSOR")) 재개. 커서는 이동하지 않습니다."
  local clear_cmd continue_prompt
  clear_cmd="$(b64dec "$CLEAR_B64")"; continue_prompt="$(continuation_prompt)"
  if [ "$manual" = "1" ]; then
    rm -f "$STATE_DIR/inject-ticket.json" "$STATE_DIR/legacy-ticket"
    echo "수동 모드: 키 전송/예약 없음. 이미 접수된 continuation은 다시 보내지 마세요."
  elif schedule_inject; then
    echo "⏳ 현재 커서 재개 예약 (pane=$PANE). 접수 확인은 inject.log 참고."
  else
    echo "⚠ 자동 재개 미예약. 진행 중 작업/초안/기존 접수를 확인한 후 수동 실행:"
    echo "  $clear_cmd → 새 세션 확인 → $continue_prompt (한 번만). advance 금지."
  fi
}

cmd_stop() {
  load_state
  rm -f "$STATE_DIR/inject-ticket.json" "$STATE_DIR/legacy-ticket"
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
  # Old detached jobs lacking an immutable reservation are intentionally inert.
  [ $# -eq 4 ] || { echo "phaseflow: failed legacy reservation missing; no keys sent"; return 1; }
  local expected_run="$1" expected_phase="$2" expected_ticket="$3" expected_identity="$4"
  load_state
  [ "$TOOL" != "codex" ] || { echo "phaseflow: failed unguarded Codex injection disabled"; return 1; }
  legacy_valid() {
    load_state
    [ "$RUN_ID" = "$expected_run" ] && [ "$CURSOR" = "$expected_phase" ] &&
      [ "$STATUS" = "active" ] && [ ! -f "$PAUSE_SENTINEL" ] &&
      [ "$(cat "$STATE_DIR/legacy-ticket" 2>/dev/null)" = "$expected_ticket" ] &&
      [ "$(tmux display-message -p -t "$PANE" '#{pid}|#{pane_id}|#{pane_pid}|#{pane_current_command}' 2>/dev/null)" = "$expected_identity" ]
  }
  sleep "$DELAY"
  legacy_valid || return 1
  tmux_send_line "$PANE" "$(b64dec "$CLEAR_B64")"
  legacy_valid || return 1
  tmux_submit "$PANE" "$TOOL"
  echo "phaseflow: keys_sent clear phase=$CURSOR runtime=$TOOL (transition unverified)"
  sleep "$GAP"
  legacy_valid || return 1
  tmux_send_line "$PANE" "$(b64dec "$CONTINUE_B64")"
  legacy_valid || return 1
  tmux_submit "$PANE" "$TOOL"
  echo "phaseflow: keys_sent continuation phase=$CURSOR runtime=$TOOL (acceptance unverified)"
}

# ─────────────────────────────────────────────────────────────────────────────
main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    init)       cmd_init "$@" ;;
    set-hook)   cmd_set_hook "$@" ;;
    load-hooks) cmd_load_hooks "$@" ;;
    status)     cmd_status ;;
    current)    cmd_current ;;
    stage)      cmd_stage ;;
    run-hooks)  cmd_run_hooks "$@" ;;
    next-stage) cmd_next_stage ;;
    advance)    cmd_advance "$@" ;;
    pause)      cmd_pause ;;
    resume)     cmd_resume "$@" ;;
    stop|abort) cmd_stop ;;
    reset)      cmd_reset ;;
    paths)      cmd_paths ;;
    __inject)   cmd___inject "$@" ;;
    ""|-h|--help)
      cat <<'USAGE'
phaseflow.sh <subcommand>
  init --pane <id> --tool <claude|codex> [--commit-each] [--delay N] [--clear-cmd C]
       [--continue-prompt P] [--stages a,b,c] [--gates a,b|auto]   (페이즈 제목 stdin, 한 줄당 하나)
  set-hook <stage> --shell|--prompt [--phase N]   그 stage(또는 Phase N 전용) 훅 본문을 stdin 으로 등록
  load-hooks [<file>]   선언적 훅 스펙(기본 hooks.spec)을 파싱해 STAGES/GATES·훅 스토어 재구성
  status                현재 페이즈/ stage / 게이트 상태 표시
  current               LLM 파싱용 현재 커서/제목/ stage (KEY=VALUE)
  stage                 현재 stage 의 훅/게이트 정보 (KEY=VALUE)
  run-hooks <stage> [--no-gate]   그 stage 의 prompt 훅 출력 + shell 훅 실행(게이트 기록)
  next-stage            현재 페이즈 안에서 stage 커서 전진(소진 시 PHASE_COMPLETE)
  advance [--pane id] [--tool t] [--force]   현재 페이즈 done, 게이트 확인 후 전진 + clear/continue 예약
  resume [--pane id] [--manual]    현재 커서 재개 (advance 아님); --manual 은 키 전송 없음
  pause | stop | reset             예약 취소/제어
  paths                 디버그: 경로/ pane 도출 확인
USAGE
      ;;
    *) die "알 수 없는 subcommand: $sub (--help 참고)" ;;
  esac
}

# Serialize state mutations and scheduling across concurrent CLI invocations.
# Worker locks each check/send separately so pause/stop can interrupt waits.
if [ "${1:-}" != "__inject" ] && [ "${PHASEFLOW_LOCK_HELD:-0}" != "1" ]; then
  exec python3 "$(dirname "$SELF")/inject.py" locked "$STATE_DIR" bash "$SELF" "$@"
fi
main "$@"
