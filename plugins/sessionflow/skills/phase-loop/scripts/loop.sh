#!/usr/bin/env bash
# loop.sh — sessionflow:phase-loop 보조 엔진
#
# phase-loop 은 phase-run 의 상태머신·tmux 주입 엔진(phaseflow.sh)을 그대로 재사용하되,
#   - 상태 네임스페이스를 'phase-loop' 으로 분리해 phase-run 과 충돌하지 않고,
#   - 각 페이즈 경계에 (xreview → commit → push → PR → handoff) 를 끼워 넣는다.
# 이 스크립트는 LLM(SKILL.md)이 호출하는 "기계적" 보조 — 경로 도출, 모드 감지,
# 워크트리 생성, phaseflow forward 만 담당한다. 실제 "작업"(구현/리뷰/커밋)은 LLM 이 한다.
#
# 서브커맨드:
#   paths                              현재 cwd 기준 세션/PHASES/HANDOFF/state 경로 도출
#   detect-mode                        remote/기여자 휴리스틱으로 personal|team 추정
#   worktree-create --slug S --base R [--first-branch B] [--parent DIR]
#                                      워크트리 + 첫 브랜치 생성, 그 워크트리의 PHASES.md 경로 echo
#   pf <args...>                       phaseflow.sh 를 'phase-loop' 네임스페이스로 forward
#
# 환경변수:
#   HBRNESS_HOME   기본 ~/.hbrness

set -euo pipefail

HBRNESS_HOME="${HBRNESS_HOME:-$HOME/.hbrness}"
STATE_NAME="phase-loop"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# phaseflow.sh 는 같은 플러그인의 phase-run 스킬에 산다 (dist 에서도 sibling 구조 보존).
PHASEFLOW="$(cd "$SELF_DIR/../../phase-run/scripts" 2>/dev/null && pwd)/phaseflow.sh"

die() { echo "loop: $*" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────────────────────
# 컨텍스트 도출 — sessionflow:handoff / phaseflow 와 동일한 워크트리 인지 규약
#   $1(선택): 대상 디렉토리. 생략 시 현재 cwd.
# 출력 전역: CTX_ROOT CTX_KEY CTX_IS_WT CTX_WT CTX_DIR
# ─────────────────────────────────────────────────────────────────────────────
resolve_ctx() {
  local target="${1:-}"
  local gc gd
  if [ -n "$target" ]; then
    gc=$(git -C "$target" rev-parse --git-common-dir 2>/dev/null || true)
    gd=$(git -C "$target" rev-parse --git-dir 2>/dev/null || true)
  else
    gc=$(git rev-parse --git-common-dir 2>/dev/null || true)
    gd=$(git rev-parse --git-dir 2>/dev/null || true)
  fi

  if [ -z "$gc" ]; then
    CTX_ROOT="${target:-$(pwd)}"
    CTX_IS_WT=0
    CTX_WT="main"
  else
    # git-common-dir 이 상대경로일 수 있어 절대경로화
    case "$gc" in
      /*) : ;;
      *)  gc="$(cd "${target:-.}" && cd "$(dirname "$gc")" && pwd)/$(basename "$gc")" ;;
    esac
    CTX_ROOT="$(cd "$(dirname "$gc")" && pwd)"
    if [ "$(cd "$(dirname "$gd")" 2>/dev/null && pwd)/$(basename "$gd")" = "$gc" ] || [ "$gd" = "$gc" ]; then
      CTX_IS_WT=0
      CTX_WT="main"
    else
      CTX_IS_WT=1
      CTX_WT="$(basename "$gd")"
    fi
  fi

  CTX_KEY="$(echo "$CTX_ROOT" | tr '/' '-')"
  if [ "$CTX_IS_WT" = "1" ]; then
    CTX_DIR="$HBRNESS_HOME/sessionflow/$CTX_KEY/worktrees/$CTX_WT"
  else
    CTX_DIR="$HBRNESS_HOME/sessionflow/$CTX_KEY"
  fi
}

cmd_paths() {
  resolve_ctx "${1:-}"
  echo "ROOT=$CTX_ROOT"
  echo "PROJECT_KEY=$CTX_KEY"
  echo "IS_WORKTREE=$CTX_IS_WT"
  echo "WORKTREE=$CTX_WT"
  echo "SESSION_DIR=$CTX_DIR"
  echo "PHASES_FILE=$CTX_DIR/PHASES.md"
  echo "HANDOFF_FILE=$CTX_DIR/HANDOFF.md"
  echo "STATE_DIR=$CTX_DIR/$STATE_NAME"
}

# ─────────────────────────────────────────────────────────────────────────────
# 모드 감지 휴리스틱 — 최종 결정은 사용자가 init 에서 1회 확인한다(이건 "추정"일 뿐).
# ─────────────────────────────────────────────────────────────────────────────
cmd_detect_mode() {
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "MODE=personal"
    echo "REASON=git 레포가 아님 — 브랜치/PR 개념 없음"
    return 0
  fi
  local remotes authors
  remotes="$(git remote 2>/dev/null | tr '\n' ',' | sed 's/,$//')"
  if [ -z "$remotes" ]; then
    echo "MODE=personal"
    echo "REASON=remote 가 없음 — push/PR 대상 없음"
    echo "REMOTES="
    return 0
  fi
  authors="$(git shortlog -sne --all 2>/dev/null | wc -l | tr -d ' ')"
  [ -n "$authors" ] || authors=1
  echo "REMOTES=$remotes"
  echo "AUTHORS=$authors"
  if [ "$authors" -ge 2 ]; then
    echo "MODE=team"
    echo "REASON=remote 있음 + 기여자 ${authors}명 → 협업 레포로 추정 (워크트리+스택+PR)"
  else
    echo "MODE=personal"
    echo "REASON=remote 있으나 단독 기여자(${authors}명) → 개인 레포로 추정 (브랜치 직접)"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# 워크트리 생성 (팀 모드 부트스트랩). 메인 체크아웃에서 호출한다.
#   --slug         워크트리/브랜치 식별자 (예: auth-feature)
#   --base         첫 브랜치를 분기할 base ref (예: origin/main, main)
#   --first-branch 첫 페이즈 브랜치명 (생략 시 <slug>/01)
#   --parent       워크트리를 만들 부모 디렉토리 (생략 시 레포 루트의 부모)
# ─────────────────────────────────────────────────────────────────────────────
cmd_worktree_create() {
  local slug="" base="" first_branch="" parent=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --slug) slug="$2"; shift 2 ;;
      --base) base="$2"; shift 2 ;;
      --first-branch) first_branch="$2"; shift 2 ;;
      --parent) parent="$2"; shift 2 ;;
      *) die "worktree-create: 알 수 없는 인자 $1" ;;
    esac
  done
  [ -n "$slug" ] || die "worktree-create: --slug 필수"
  [ -n "$base" ] || die "worktree-create: --base 필수"
  git rev-parse --git-dir >/dev/null 2>&1 || die "worktree-create: git 레포가 아님"

  local repo_root repo_name wt_path
  repo_root="$(git rev-parse --show-toplevel)"
  repo_name="$(basename "$repo_root")"
  [ -n "$parent" ] || parent="$(dirname "$repo_root")"
  [ -n "$first_branch" ] || first_branch="$slug/01"
  wt_path="$parent/${repo_name}-${slug}"

  [ -e "$wt_path" ] && die "worktree-create: 경로가 이미 존재함: $wt_path"
  if git show-ref --verify --quiet "refs/heads/$first_branch"; then
    die "worktree-create: 브랜치가 이미 존재함: $first_branch"
  fi

  git worktree add "$wt_path" -b "$first_branch" "$base" >&2

  # 새 워크트리의 PHASES.md 경로(= phaseflow/handoff 네임스페이스)를 계산해 echo
  resolve_ctx "$wt_path"
  echo "WORKTREE=$wt_path"
  echo "FIRST_BRANCH=$first_branch"
  echo "BASE=$base"
  echo "WT_NAME=$CTX_WT"
  echo "SESSION_DIR=$CTX_DIR"
  echo "PHASES_FILE=$CTX_DIR/PHASES.md"
  echo "HANDOFF_FILE=$CTX_DIR/HANDOFF.md"
}

# ─────────────────────────────────────────────────────────────────────────────
# phaseflow forward — 'phase-loop' 네임스페이스로 phase-run 엔진 호출.
# init/advance/current/status/pause/resume/stop/reset/paths 그대로 전달.
# ─────────────────────────────────────────────────────────────────────────────
cmd_pf() {
  [ -f "$PHASEFLOW" ] || die "phaseflow.sh 를 찾을 수 없음: $PHASEFLOW (phase-run 스킬이 설치돼 있어야 함)"
  PHASEFLOW_STATE_DIR_NAME="$STATE_NAME" bash "$PHASEFLOW" "$@"
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    paths)            cmd_paths "$@" ;;
    detect-mode)      cmd_detect_mode ;;
    worktree-create)  cmd_worktree_create "$@" ;;
    pf)               cmd_pf "$@" ;;
    ""|-h|--help)
      cat <<'USAGE'
loop.sh <subcommand>
  paths [dir]                        세션/PHASES/HANDOFF/state 경로 도출 (기본 cwd)
  detect-mode                        personal|team 추정 (휴리스틱)
  worktree-create --slug S --base R [--first-branch B] [--parent DIR]
  pf <phaseflow args...>             phaseflow.sh 를 'phase-loop' 네임스페이스로 호출
USAGE
      ;;
    *) die "알 수 없는 subcommand: $sub (--help 참고)" ;;
  esac
}

main "$@"
