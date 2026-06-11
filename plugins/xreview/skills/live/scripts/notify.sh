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
elapsed=0

while :; do
  if [ -s "$result" ]; then
    xr_tmux_send_line "$launcher_pane" \
      "[xreview:live] 리뷰 완료 (${slug}) — Read ${result} 로 결과 열어서 요약해줘." \
      "$launcher_tool"
    exit 0
  fi
  # Run ended without a result? (session gone, or reviewer pane died)
  if ! xr_session_exists "$sess"; then
    xr_tmux_send_line "$launcher_pane" \
      "[xreview:live] 리뷰 세션(${slug})이 결과 없이 종료됨. /xreview:live status 로 확인." \
      "$launcher_tool"
    exit 0
  fi
  if [ "$(xr_session_pane_dead "$sess")" = "1" ]; then
    # Give a brief grace window for a last write, then report.
    sleep "$interval"
    if [ -s "$result" ]; then
      xr_tmux_send_line "$launcher_pane" \
        "[xreview:live] 리뷰 완료 (${slug}) — Read ${result} 로 결과 열어서 요약해줘." \
        "$launcher_tool"
    else
      xr_tmux_send_line "$launcher_pane" \
        "[xreview:live] 리뷰어(${slug})가 결과 파일 없이 종료됨. /xreview:live peek 로 확인." \
        "$launcher_tool"
    fi
    exit 0
  fi
  sleep "$interval"
  elapsed=$((elapsed + interval))
  if [ "$elapsed" -ge "$timeout" ]; then
    xr_tmux_send_line "$launcher_pane" \
      "[xreview:live] 리뷰(${slug}) 대기 시간 초과(${timeout}s). /xreview:live peek 로 진행 상황 확인." \
      "$launcher_tool"
    exit 0
  fi
done
