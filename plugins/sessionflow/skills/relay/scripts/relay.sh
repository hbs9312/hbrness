#!/usr/bin/env bash
# relay — 바통 모델 페이즈 러너의 상태/계량 엔진.
#
# phase-run 과 목적은 같다(긴 작업을 페이즈로 쪼개고 페이즈마다 fresh 컨텍스트로
# 간다). 방식이 다르다. phase-run 은 자기 pane 에 /clear 를 되쏘아 **세션 자신을**
# 갈아치우고, relay 는 오케스트레이터가 살아남은 채 **페이즈마다 서브에이전트를
# 새로 띄운다.** 그래서 tmux 키 주입이 없고(=터미널 무관), 페이즈 실패 시 그냥 다시
# 디스패치하면 되며, 페이즈를 병렬로도 돌릴 수 있다.
#
# 대신 오케스트레이터 컨텍스트가 누적될 위험이 생긴다. 이 스크립트가 하는 일은
# 그 누적을 **막는 규율을 파일로 강제하고, 실제로 얼마나 붙었는지 재는 것**이다.
#   - 리포트/리뷰/핸드오프를 정해진 자리에 보관한다(오케스트레이터가 다시 안 읽어도 됨).
#   - 핸드오프에 필수 섹션이 있는지 검사한다. 다음 서브에이전트는 컨텍스트가 0이므로
#     여기 빠진 것은 그대로 소실된다.
#   - 페이즈마다 리포트·리뷰·핸드오프 크기를 METRICS.tsv 에 적는다.
#
# 상태: {HBRNESS_HOME}/sessionflow/<project-key>/relay/   (워크트리면 worktrees/<wt>/relay/)
#       HANDOFF.md 는 그 부모 = sessionflow:handoff 와 같은 자리.
#
# Usage:
#   relay.sh init --plan <file> [--review none|cleanroom|xreview|both] [--mode auto|confirm]
#   relay.sh paths | status | metrics
#   relay.sh report <file>            # 이번 페이즈 서브에이전트 리포트 보관
#   relay.sh review <file>            # 이번 페이즈 리뷰 findings 보관
#   relay.sh handoff <file>           # 검사 후 HANDOFF.md 로 설치
#   relay.sh advance                  # 다음 페이즈로
#   relay.sh pause | resume | stop | reset
set -euo pipefail

HBRNESS_HOME="${HBRNESS_HOME:-$HOME/.hbrness}"
STATE_DIR_NAME="${RELAY_STATE_DIR_NAME:-relay}"
MAX_PHASES="${RELAY_MAX_PHASES:-50}"

die() { echo "relay: $*" >&2; exit 1; }
log() { echo "relay: $*" >&2; }

# phase-run/handoff 와 동일한 워크트리 인지 규약.
resolve_state_dir() {
  local git_common git_dir project_root is_worktree wt_name project_key
  git_common=$(git rev-parse --git-common-dir 2>/dev/null || true)
  git_dir=$(git rev-parse --git-dir 2>/dev/null || true)

  if [ -z "$git_common" ]; then
    project_root=$(pwd); is_worktree=0
  else
    project_root=$(cd "$(dirname "$git_common")" && pwd)
    if [ "$git_dir" = "$git_common" ]; then is_worktree=0
    else is_worktree=1; wt_name=$(basename "$git_dir"); fi
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
PLAN_FILE="$STATE_DIR/PLAN.md"
METRICS="$STATE_DIR/METRICS.tsv"
PHASES_DIR="$STATE_DIR/phases"
PAUSED="$STATE_DIR/PAUSED"
HANDOFF_FILE="$(dirname "$STATE_DIR")/HANDOFF.md"

load_state() {
  [ -f "$STATE_ENV" ] || die "활성 relay 가 없습니다 ($STATE_ENV). 먼저 'init' 하세요."
  # shellcheck disable=SC1090
  . "$STATE_ENV"
  PHASE_IDX="${PHASE_IDX:-1}"
  REVIEW="${REVIEW:-none}"
  MODE="${MODE:-confirm}"
  TOTAL="${TOTAL:-0}"
}

save_state() {
  { printf 'PHASE_IDX=%s\n' "$PHASE_IDX"
    printf 'TOTAL=%s\n' "$TOTAL"
    printf 'REVIEW=%s\n' "$REVIEW"
    printf 'MODE=%s\n' "$MODE"
    printf 'STARTED=%s\n' "$STARTED"
  } > "$STATE_ENV"
}

pad() { printf '%02d' "$1"; }

# 파일 하나의 줄/바이트/대략 토큰. 토큰은 정확할 필요가 없다 — 페이즈 간 비교가 목적이라
# 한글이 섞인 산문 기준으로 바이트/3 이면 자릿수는 맞는다.
measure() {
  local f="$1" b l
  [ -f "$f" ] || { printf '0\t0\t0'; return; }
  b=$(wc -c < "$f" | tr -d ' '); l=$(wc -l < "$f" | tr -d ' ')
  printf '%s\t%s\t%s' "$l" "$b" "$((b / 3))"
}

metric_row() { # <phase> <kind> <file>
  mkdir -p "$STATE_DIR"
  [ -f "$METRICS" ] || printf 'phase\tkind\tlines\tbytes\t~tokens\tat\n' > "$METRICS"
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$(measure "$3")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$METRICS"
}

# 핸드오프 필수 섹션. 다음 서브에이전트는 컨텍스트가 0이라, 여기 없는 것은 소실된다.
# 코드 설명은 일부러 요구하지 않는다 — 다음 서브에이전트가 레포를 직접 읽는 게 규칙이고,
# 요약의 요약이 쌓이는 게 이 모델의 유일한 실패 경로다.
REQUIRED_SECTIONS='## 지금 상태
## 다음 페이즈가 해야 할 것
## 건드리면 안 되는 것
## 이미 시도했다 실패한 것
## 열린 질문'

check_handoff() {
  local f="$1" missing=0 sec
  [ -s "$f" ] || die "핸드오프 파일이 비어 있습니다: $f"
  while IFS= read -r sec; do
    [ -n "$sec" ] || continue
    grep -qF "$sec" "$f" || { log "빠진 섹션: $sec"; missing=1; }
  done <<< "$REQUIRED_SECTIONS"
  [ "$missing" -eq 0 ] || die "핸드오프에 필수 섹션이 빠졌습니다. 다음 서브에이전트는 컨텍스트가 0이라 여기 없는 건 영영 모릅니다."
  grep -qiE '(TODO|TBD|\bXXX\b|채워넣기|나중에 적기)' "$f" \
    && die "핸드오프에 미완성 표시가 남아 있습니다. 채우고 다시 부르세요."
  return 0
}

cmd_init() {
  local plan="" review="none" mode="confirm"
  while [ $# -gt 0 ]; do
    case "$1" in
      --plan)   plan="$2"; shift 2 ;;
      --review) review="$2"; shift 2 ;;
      --mode)   mode="$2"; shift 2 ;;
      *) die "init: 알 수 없는 인자 $1" ;;
    esac
  done
  [ -n "$plan" ] || die "init: --plan <file> 이 필요합니다"
  [ -f "$plan" ] || die "init: 계획 파일이 없습니다: $plan"
  case "$review" in none|cleanroom|xreview|both) ;; *) die "init: --review 는 none|cleanroom|xreview|both" ;; esac
  case "$mode" in auto|confirm) ;; *) die "init: --mode 는 auto|confirm" ;; esac
  [ -f "$STATE_ENV" ] && die "이미 진행 중인 relay 가 있습니다. 'status' 로 보거나 'reset' 하세요."

  local total
  total=$(grep -cE '^##[[:space:]]+Phase[[:space:]]+[0-9]+' "$plan" || true)
  [ "$total" -ge 1 ] || die "계획에서 페이즈를 못 찾았습니다. '## Phase 1 — 제목' 형식의 헤딩이 필요합니다."
  [ "$total" -le "$MAX_PHASES" ] || die "페이즈가 $MAX_PHASES 개를 넘습니다 ($total)."

  mkdir -p "$STATE_DIR" "$PHASES_DIR"
  cp "$plan" "$PLAN_FILE"
  PHASE_IDX=1; TOTAL="$total"; REVIEW="$review"; MODE="$mode"
  STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  save_state
  printf 'relay 시작 — 페이즈 %d개, review=%s, mode=%s\n' "$total" "$review" "$mode"
  printf '  상태  : %s\n  계획  : %s\n  핸드오프: %s\n' "$STATE_DIR" "$PLAN_FILE" "$HANDOFF_FILE"
}

cmd_paths() {
  printf 'state_dir=%s\nplan=%s\nphases_dir=%s\nhandoff=%s\nmetrics=%s\npaused=%s\n' \
    "$STATE_DIR" "$PLAN_FILE" "$PHASES_DIR" "$HANDOFF_FILE" "$METRICS" \
    "$([ -f "$PAUSED" ] && echo yes || echo no)"
}

cmd_status() {
  [ -f "$STATE_ENV" ] || { echo "활성 relay 없음."; return 0; }
  load_state
  printf '● relay  phase %d / %d   review=%s  mode=%s%s\n' \
    "$PHASE_IDX" "$TOTAL" "$REVIEW" "$MODE" "$([ -f "$PAUSED" ] && echo '  [PAUSED]' || echo '')"
  printf '  시작 : %s\n' "$STARTED"
  local n; n="$(pad "$PHASE_IDX")"
  for kind in report review handoff; do
    local f="$PHASES_DIR/$n-$kind.md"
    [ -f "$f" ] && printf '  %-8s: %s\n' "$kind" "$f"
  done
  [ -f "$HANDOFF_FILE" ] && printf '  설치본  : %s\n' "$HANDOFF_FILE"
  return 0
}

cmd_archive() { # <kind> <file>
  local kind="$1" src="$2" n dst
  load_state
  [ -f "$src" ] || die "$kind: 파일이 없습니다: $src"
  n="$(pad "$PHASE_IDX")"
  mkdir -p "$PHASES_DIR"
  dst="$PHASES_DIR/$n-$kind.md"
  cp "$src" "$dst"
  metric_row "$PHASE_IDX" "$kind" "$dst"
  printf '%s 보관: %s\n' "$kind" "$dst"
}

cmd_handoff() {
  local src="$1" n
  load_state
  [ -f "$src" ] || die "handoff: 파일이 없습니다: $src"
  check_handoff "$src"
  n="$(pad "$PHASE_IDX")"
  mkdir -p "$PHASES_DIR" "$(dirname "$HANDOFF_FILE")"
  cp "$src" "$PHASES_DIR/$n-handoff.md"
  cp "$src" "$HANDOFF_FILE"
  metric_row "$PHASE_IDX" "handoff" "$HANDOFF_FILE"
  printf '핸드오프 설치: %s\n' "$HANDOFF_FILE"
}

cmd_advance() {
  load_state
  [ -f "$PAUSED" ] && die "일시정지 상태입니다. 'resume' 후 다시 부르세요."
  [ -f "$PHASES_DIR/$(pad "$PHASE_IDX")-handoff.md" ] \
    || die "이번 페이즈 핸드오프가 아직 없습니다. 'handoff <file>' 를 먼저 부르세요."
  if [ "$PHASE_IDX" -ge "$TOTAL" ]; then
    printf '마지막 페이즈(%d/%d)입니다. 더 전진할 곳이 없습니다 — 마무리하고 stop 하세요.\n' "$PHASE_IDX" "$TOTAL"
    return 0
  fi
  PHASE_IDX=$((PHASE_IDX + 1))
  save_state
  printf '다음 페이즈: %d / %d\n' "$PHASE_IDX" "$TOTAL"
}

cmd_metrics() {
  [ -f "$METRICS" ] || { echo "아직 기록 없음."; return 0; }
  load_state 2>/dev/null || true
  column -t -s "$(printf '\t')" "$METRICS" 2>/dev/null || cat "$METRICS"
  echo
  awk -F'\t' 'NR>1 {sum[$2]+=$5; tot+=$5} END {
    for (k in sum) printf "합계 %-8s ~%d 토큰\n", k, sum[k];
    printf "─────────────────────────\n오케스트레이터가 읽은 총량 ~%d 토큰\n", tot
  }' "$METRICS"
  echo
  echo "※ 리포트+리뷰+핸드오프만 센 값이다. 오케스트레이터 자신의 툴 호출·판단 턴은 빠져 있으니,"
  echo "  실제 누적은 이것보다 크다. 이 숫자가 바통 모델의 하한이다."
}

cmd_reset() {
  [ -d "$STATE_DIR" ] || { echo "지울 상태 없음."; return 0; }
  case "$STATE_DIR" in
    "$HBRNESS_HOME"/sessionflow/*) rm -rf "$STATE_DIR" ;;
    *) die "안전장치: 예상 밖 경로라 지우지 않습니다 ($STATE_DIR)" ;;
  esac
  echo "relay 상태를 지웠습니다. HANDOFF.md 는 그대로 둡니다."
}

case "${1:-}" in
  init)    shift; cmd_init "$@" ;;
  paths)   cmd_paths ;;
  status)  cmd_status ;;
  report)  shift; cmd_archive report "${1:-}" ;;
  review)  shift; cmd_archive review "${1:-}" ;;
  handoff) shift; cmd_handoff "${1:-}" ;;
  advance) cmd_advance ;;
  metrics) cmd_metrics ;;
  pause)   load_state; touch "$PAUSED"; echo "일시정지. 'resume' 으로 재개." ;;
  resume)  load_state; rm -f "$PAUSED"; echo "재개." ;;
  stop)    load_state; rm -f "$STATE_ENV"; echo "relay 종료. 기록(phases/, METRICS.tsv)은 남습니다." ;;
  reset)   cmd_reset ;;
  ""|-h|--help) sed -n '2,26p' "$0" ;;
  *) die "알 수 없는 명령: $1" ;;
esac
