#!/usr/bin/env bash
# Background watcher: poll for the reviewer's RESULT file (or end-of-run), then
# inject a one-line completion notice into the launcher pane.
#
# Usage: notify.sh <launcher-pane> <work-dir> <launcher-tool> <slug>
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

launcher_pane="${1:-}"
work="${2:-}"
launcher_tool="${3:-}"
slug="${4:-}"
[ -n "$launcher_pane" ] && [ -n "$work" ] && [ -n "$slug" ] || exit 0

result="$work/REVIEW_RESULT.md"
sess="$(xr_session_name "$slug")"
timeout="${XRLIVE_WATCH_TIMEOUT:-7200}"   # seconds (default 2h)
interval="${XRLIVE_WATCH_INTERVAL:-3}"
stuck_after="${XRLIVE_STUCK_AFTER:-2}"    # consecutive detections before stuck ping
elapsed=0
stuck_streak=0
stuck_pinged=0

ping() { xr_tmux_send_line "$launcher_pane" "$1" "$launcher_tool"; }

while :; do
  if [ -s "$result" ]; then
    xr_set_watch_state "$work" done "결과 파일 작성됨"
    ping "[xreview:live] 리뷰 완료 (${slug}) — Read ${result} 로 결과 열어서 요약해줘."
    exit 0
  fi
  # Run ended without a result? (session gone, or reviewer pane died)
  if ! xr_session_exists "$sess"; then
    xr_set_watch_state "$work" gone "세션이 결과 없이 종료됨"
    ping "[xreview:live] 리뷰 세션(${slug})이 결과 없이 종료됨. /xreview:status 로 확인."
    exit 0
  fi
  if [ "$(xr_session_pane_dead "$sess")" = "1" ]; then
    # Give a brief grace window for a last write, then report.
    sleep "$interval"
    if [ -s "$result" ]; then
      xr_set_watch_state "$work" done "결과 파일 작성됨"
      ping "[xreview:live] 리뷰 완료 (${slug}) — Read ${result} 로 결과 열어서 요약해줘."
    else
      xr_set_watch_state "$work" ended-no-result "리뷰어가 결과 파일 없이 종료"
      ping "[xreview:live] 리뷰어(${slug})가 결과 파일 없이 종료됨. /xreview:live peek 로 확인."
    fi
    exit 0
  fi
  # Alive but no result yet — is it hung on a trust/permission prompt it can't
  # answer? Require repeated detection to avoid false positives from review prose,
  # and ping only once so a later user answer + completion still flows normally.
  if xr_detect_stuck_prompt "$(xr_capture_pane "$sess" 40)"; then
    stuck_streak=$((stuck_streak + 1))
    if [ "$stuck_streak" -ge "$stuck_after" ] && [ "$stuck_pinged" -eq 0 ]; then
      xr_set_watch_state "$work" stuck "trust/권한 프롬프트 감지 — peek 로 응답 필요"
      ping "[xreview:live] 리뷰어(${slug})가 trust/권한 프롬프트에서 멈춤 — /xreview:live peek 로 응답하거나 /xreview:stop 후 재시작."
      stuck_pinged=1
    fi
  else
    stuck_streak=0
    if [ "$stuck_pinged" -eq 1 ]; then          # prompt cleared (e.g. user answered)
      xr_set_watch_state "$work" running "프롬프트 해소됨 — 재개"
      stuck_pinged=0
    fi
  fi
  sleep "$interval"
  elapsed=$((elapsed + interval))
  if [ "$elapsed" -ge "$timeout" ]; then
    xr_set_watch_state "$work" timeout "대기 시간 초과(${timeout}s)"
    ping "[xreview:live] 리뷰(${slug}) 대기 시간 초과(${timeout}s). /xreview:live peek 로 진행 상황 확인."
    exit 0
  fi
done
