#!/usr/bin/env bash
# testflow capture — 헤드리스 브라우저로 웹 화면 한 장을 찍는다. 사용자 화면에는 창이 뜨지 않는다.
#
# Usage: capture.sh <url> [--out <path>] [--viewport WxH] [--device "<name>"] [--full-page]
#                   [--wait-for <selector>] [--wait-ms <ms>] [--color-scheme light|dark]
#                   [--lang <locale>] [--timezone <tz>] [--browser chromium|firefox|webkit]
#                   [--timeout <ms>] [--load-storage <file>]
#
# --device 를 주면 그 기기의 기본 브라우저로 찍는다 (iPhone·iPad → webkit, Pixel·Galaxy → chromium).
#
# 출력 (KEY=VALUE):
#   SCREENSHOT=<절대경로>  SIZE=<가로x세로>  PLAYWRIGHT=<버전> (<project|npx>)
# 실패 코드:
#   2 인자 오류 · 3 URL 에 닿지 않음 (URL_UNREACHABLE=1) · 4 브라우저 미설치 (NEED_BROWSER_INSTALL=1) · 5 그 밖의 캡처 실패
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$SCRIPT_DIR/lib.sh"

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

URL=""; OUT=""; VIEWPORT=""; DEVICE=""; FULL=0; WAIT_SEL=""; WAIT_MS=""; SCHEME=""
LOCALE="ko-KR"; TZONE="Asia/Seoul"; BROWSER="chromium"; TIMEOUT="30000"; STORAGE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --viewport) VIEWPORT="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --full-page) FULL=1; shift ;;
    --wait-for) WAIT_SEL="$2"; shift 2 ;;
    --wait-ms) WAIT_MS="$2"; shift 2 ;;
    --color-scheme) SCHEME="$2"; shift 2 ;;
    --lang) LOCALE="$2"; shift 2 ;;
    --timezone) TZONE="$2"; shift 2 ;;
    --browser) BROWSER="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --load-storage) STORAGE="$2"; shift 2 ;;
    -h|--help) usage ;;
    -*) echo "ERROR=unknown option $1" >&2; usage ;;
    *) if [ -z "$URL" ]; then URL="$1"; shift; else echo "ERROR=extra argument $1" >&2; usage; fi ;;
  esac
done
[ -n "$URL" ] || usage
# 기기 에뮬레이션을 안 쓰면 데스크톱 기본 뷰포트를 쓴다. 기기를 쓰면 기기 값이 뷰포트를 정한다.
if [ -z "$DEVICE" ] && [ -z "$VIEWPORT" ]; then VIEWPORT="1440x900"; fi

ROOT="$(tf_root)"
tf_ensure_gitignore "$ROOT"

if [ -z "$OUT" ]; then
  slug="$(printf '%s' "$URL" | sed -E 's#^[a-z]+://##; s#[^A-Za-z0-9]+#-#g; s#^-+|-+$##g' | cut -c1-60)"
  [ -n "$DEVICE" ] && slug="$slug-$(printf '%s' "$DEVICE" | tr -cs 'A-Za-z0-9' '-' | sed 's/-$//')"
  OUT="$ROOT/.testflow/screenshots/$(date +%Y%m%d-%H%M%S)-${slug:-page}.png"
fi
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac
mkdir -p "$(dirname "$OUT")"

# dev 서버가 떠 있는지 먼저 본다. 브라우저 타임아웃까지 기다리지 않게.
case "$URL" in
  http://*|https://*)
    # 연결 자체가 안 될 때(6 이름 해석 실패, 7 연결 거부)만 막는다.
    # 첫 컴파일이 느린 dev 서버는 응답 전에 타임아웃(28)이 날 수 있어서 통과시킨다.
    rc=0; curl -sSk -o /dev/null --connect-timeout 3 -m 5 "$URL" 2>/dev/null || rc=$?
    if [ "$rc" = 6 ] || [ "$rc" = 7 ]; then
      echo "URL_UNREACHABLE=1"
      echo "ERROR=$URL 에 연결하지 못했습니다. dev 서버가 떠 있는지, 포트가 맞는지 확인하세요."
      exit 3
    fi
    ;;
esac

PROJECT_PW="$(tf_project_playwright_version "$PWD")"
[ -n "$PROJECT_PW" ] || PROJECT_PW="$(tf_project_playwright_version "$ROOT")"
if [ -n "$PROJECT_PW" ]; then
  PW_VERSION="$PROJECT_PW"; PW_SOURCE="project"
else
  PW_VERSION="${TESTFLOW_PLAYWRIGHT_VERSION:-$TF_DEFAULT_PLAYWRIGHT_VERSION}"; PW_SOURCE="npx"
fi
# 프로젝트 버전과 같은 CLI 를 쓴다. 브라우저 빌드가 버전마다 다르기 때문이다.
PW=(npx --yes "playwright@$PW_VERSION")

args=(screenshot --browser "$BROWSER" --lang "$LOCALE" --timezone "$TZONE" --timeout "$TIMEOUT")
[ -n "$DEVICE" ] && args+=(--device "$DEVICE")
[ -n "$VIEWPORT" ] && args+=(--viewport-size "${VIEWPORT/x/,}")
[ "$FULL" = 1 ] && args+=(--full-page)
[ -n "$WAIT_SEL" ] && args+=(--wait-for-selector "$WAIT_SEL")
[ -n "$WAIT_MS" ] && args+=(--wait-for-timeout "$WAIT_MS")
[ -n "$SCHEME" ] && args+=(--color-scheme "$SCHEME")
[ -n "$STORAGE" ] && args+=(--load-storage "$STORAGE")

log="$(mktemp)"
trap 'rm -f "$log"' EXIT
if ! "${PW[@]}" "${args[@]}" "$URL" "$OUT" >"$log" 2>&1; then
  if grep -qE "Executable doesn't exist|Please run the following command to download new browsers" "$log"; then
    # --device 를 주면 Playwright 가 그 기기의 기본 브라우저를 쓴다 (iPhone·iPad 는 webkit).
    # 그래서 --browser 값이 아니라 에러에 찍힌 실행 파일 경로로 필요한 브라우저를 고른다.
    missing="$(grep -oE '(chromium_headless_shell|chromium|webkit|firefox)-[0-9]+' "$log" | head -1 || true)"
    case "$missing" in
      chromium_headless_shell-*) install_args="--only-shell chromium"; need="chromium" ;;
      chromium-*) install_args="chromium"; need="chromium" ;;
      webkit-*) install_args="webkit"; need="webkit" ;;
      firefox-*) install_args="firefox"; need="firefox" ;;
      *) install_args="$BROWSER"; need="$BROWSER" ;;
    esac
    echo "NEED_BROWSER_INSTALL=1"
    echo "BROWSER_NEEDED=$need"
    echo "INSTALL_CMD=npx --yes playwright@$PW_VERSION install $install_args"
    echo "PLAYWRIGHT=$PW_VERSION ($PW_SOURCE)"
    exit 4
  fi
  echo "ERROR=캡처 실패"
  tail -n 30 "$log"
  exit 5
fi

echo "SCREENSHOT=$OUT"
size="$(tf_png_size "$OUT")"
[ -n "$size" ] && echo "SIZE=$size"
echo "PLAYWRIGHT=$PW_VERSION ($PW_SOURCE)"
