#!/usr/bin/env bash
# testflow vr — Playwright visual regression 을 Docker 컨테이너에서 돌린다.
# 기준 이미지를 만들 때와 비교할 때 같은 이미지(같은 OS·폰트·브라우저)를 써서 macOS·CI 렌더링 차이를 없앤다.
#
# Usage: vr.sh <test|update|build|clean> [options] [-- <playwright test 인자>]
#   test     컨테이너에서 npx playwright test
#   update   컨테이너에서 npx playwright test --update-snapshots (기준 이미지 갱신)
#   build    이미지만 빌드
#   clean    이 프로젝트의 node_modules 볼륨 삭제
# Options:
#   --dir <subdir>          playwright.config 가 있는 하위 디렉토리 (기본: 저장소 루트)
#   --platform <p>          linux/arm64 | linux/amd64 (기본: Docker 호스트 아키텍처)
#   --pw-version <ver>      Playwright 버전 (기본: 프로젝트에 설치된 @playwright/test)
#   --env NAME[=VALUE]      컨테이너에 넘길 환경 변수 (여러 번 가능)
#   --rebuild               이미지를 다시 빌드
#
# 출력 (KEY=VALUE): IMAGE, VOLUME, RESULT=pass|fail, DIFF=<경로> (실패한 비교마다)
# 실패 코드: 2 인자·프로젝트 오류 · 3 Docker 없음 · 그 밖에는 playwright test 의 종료 코드
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck source=lib.sh
. "$SCRIPT_DIR/lib.sh"

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

ACTION="${1:-}"
case "$ACTION" in
  test|update|build|clean) shift ;;
  -h|--help|"") usage ;;
  *) echo "ERROR=unknown action $ACTION"; usage ;;
esac

DIR="."; PLATFORM=""; PW_VERSION=""; REBUILD=0; ENVS=(); PW_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --pw-version) PW_VERSION="$2"; shift 2 ;;
    --env) ENVS+=(-e "$2"); shift 2 ;;
    --rebuild) REBUILD=1; shift ;;
    --) shift; PW_ARGS=("$@"); break ;;
    -h|--help) usage ;;
    *) echo "ERROR=unknown option $1"; usage ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "DOCKER=missing"; exit 3
fi
if ! DOCKER_ARCH="$(docker info --format '{{.Architecture}}' 2>/dev/null)" || [ -z "$DOCKER_ARCH" ]; then
  echo "DOCKER=not-running"; echo "ERROR=Docker 데몬이 꺼져 있습니다. Docker Desktop 을 켜세요."; exit 3
fi
if [ -z "$PLATFORM" ]; then
  case "$DOCKER_ARCH" in
    aarch64|arm64) PLATFORM="linux/arm64" ;;
    *) PLATFORM="linux/amd64" ;;
  esac
fi
ARCH_TAG="${PLATFORM#linux/}"

ROOT="$(tf_root)"
KEY="$(printf '%s' "$ROOT" | shasum -a 256 | cut -c1-12)"
VOLUME="testflow-nm-$KEY-$ARCH_TAG"

if [ "$ACTION" = clean ]; then
  docker volume rm -f "$VOLUME" >/dev/null
  echo "REMOVED_VOLUME=$VOLUME"
  imgs="$(docker image ls --format '{{.Repository}}:{{.Tag}}' 'testflow-pw' 2>/dev/null | tr '\n' ' ')"
  [ -n "$imgs" ] && echo "IMAGES=$imgs(지우려면 docker image rm)"
  exit 0
fi

DIR="${DIR%/}"; [ -n "$DIR" ] || DIR="."
if [ "$DIR" = "." ]; then WORKDIR="$ROOT"; else WORKDIR="$ROOT/$DIR"; fi
[ -d "$WORKDIR" ] || { echo "ERROR=$WORKDIR 디렉토리가 없습니다."; exit 2; }

if [ -z "$PW_VERSION" ]; then
  PW_VERSION="$(tf_project_playwright_version "$WORKDIR")"
  [ -n "$PW_VERSION" ] || PW_VERSION="$(tf_project_playwright_version "$ROOT")"
fi
if [ -z "$PW_VERSION" ]; then
  echo "NO_PLAYWRIGHT=1"
  echo "ERROR=프로젝트에 @playwright/test 가 설치돼 있지 않습니다. 호스트에서 의존성을 설치하거나 --pw-version 을 주세요."
  exit 2
fi

IMAGE="testflow-pw:$PW_VERSION-$ARCH_TAG"
if [ "$REBUILD" = 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  built=0
  # 새 버전은 noble(Ubuntu 24.04), 오래된 버전은 jammy 이미지만 있다.
  for distro in noble jammy; do
    if docker build --platform "$PLATFORM" --build-arg "PW_VERSION=$PW_VERSION" --build-arg "PW_DISTRO=$distro" \
         -t "$IMAGE" -f "$PLUGIN_DIR/assets/Dockerfile.vr" "$PLUGIN_DIR/assets" >&2; then
      built=1; break
    fi
  done
  [ "$built" = 1 ] || { echo "ERROR=이미지 빌드 실패 (mcr.microsoft.com/playwright:v$PW_VERSION-*)"; exit 2; }
fi
echo "IMAGE=$IMAGE"
[ "$ACTION" = build ] && exit 0

# 컨테이너 안에서 쓸 패키지 매니저 명령. 호스트(macOS)의 node_modules 는 볼륨으로 가리고 Linux 용으로 새로 설치한다.
if [ -f "$ROOT/pnpm-lock.yaml" ]; then
  LOCK="$ROOT/pnpm-lock.yaml"; PM=pnpm; INSTALL="pnpm install --frozen-lockfile"
elif [ -f "$ROOT/yarn.lock" ]; then
  LOCK="$ROOT/yarn.lock"; PM=yarn
  if [ -f "$ROOT/.yarnrc.yml" ]; then INSTALL="yarn install --immutable"; else INSTALL="yarn install --frozen-lockfile"; fi
elif [ -f "$ROOT/package-lock.json" ]; then
  LOCK="$ROOT/package-lock.json"; PM=npm; INSTALL="npm ci --no-audit --no-fund"
else
  echo "ERROR=저장소 루트에 lockfile(package-lock.json, pnpm-lock.yaml, yarn.lock)이 없습니다."; exit 2
fi
LOCK_HASH="$(cat "$LOCK" "$ROOT/package.json" 2>/dev/null | shasum -a 256 | cut -c1-16)-$PW_VERSION"
echo "VOLUME=$VOLUME"

HOST_IDS=()
# Linux 호스트에서는 컨테이너(root)가 만든 파일을 호스트 사용자 소유로 돌려놓는다. macOS Docker Desktop 은 필요 없다.
if [ "$(uname -s)" = Linux ]; then
  HOST_IDS=(-e "TF_HOST_UID=$(id -u)" -e "TF_HOST_GID=$(id -g)")
fi

INNER='
set -e
if [ "$(cat node_modules/.testflow-lock 2>/dev/null)" != "$TF_LOCK_HASH" ]; then
  echo "[testflow] 의존성 설치 (첫 실행이거나 lockfile 이 바뀜)" >&2
  if [ "$TF_PM" != npm ]; then
    if command -v corepack >/dev/null 2>&1; then corepack enable >/dev/null 2>&1; else npm i -g "$TF_PM" >/dev/null 2>&1; fi
  fi
  find node_modules -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  eval "$TF_INSTALL" >&2
  echo "$TF_LOCK_HASH" > node_modules/.testflow-lock
fi
touch /tmp/.testflow-start
cd "/work/$TF_DIR"
set +e
if [ "$TF_MODE" = update ]; then npx playwright test --update-snapshots "$@"; else npx playwright test "$@"; fi
rc=$?
if [ -n "${TF_HOST_UID:-}" ]; then
  find /work -path /work/node_modules -prune -o -newer /tmp/.testflow-start -user 0 -print0 \
    | xargs -0 -r chown "$TF_HOST_UID:$TF_HOST_GID"
fi
exit $rc
'

set +e
docker run --rm --init --ipc=host --platform "$PLATFORM" \
  --add-host=host.docker.internal:host-gateway \
  -v "$ROOT":/work -v "$VOLUME":/work/node_modules -w /work \
  -e "TF_LOCK_HASH=$LOCK_HASH" -e "TF_PM=$PM" -e "TF_INSTALL=$INSTALL" -e "TF_DIR=$DIR" -e "TF_MODE=$ACTION" \
  -e COREPACK_ENABLE_DOWNLOAD_PROMPT=0 -e NPM_CONFIG_UPDATE_NOTIFIER=false \
  ${HOST_IDS[@]+"${HOST_IDS[@]}"} ${ENVS[@]+"${ENVS[@]}"} \
  "$IMAGE" bash -c "$INNER" testflow ${PW_ARGS[@]+"${PW_ARGS[@]}"}
rc=$?
set -e

if [ "$rc" = 0 ]; then
  echo "RESULT=pass"
else
  echo "RESULT=fail"
  if [ -d "$WORKDIR/test-results" ]; then
    find "$WORKDIR/test-results" -name '*-diff.png' 2>/dev/null | head -20 | sed 's/^/DIFF=/'
  fi
fi
exit "$rc"
