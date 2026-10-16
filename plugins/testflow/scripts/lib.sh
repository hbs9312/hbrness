# testflow 스크립트 공통 함수. source 해서 쓴다.

# 기본 Playwright 버전. 프로젝트에 Playwright 가 없을 때 npx 로 받는 버전이다.
# TESTFLOW_PLAYWRIGHT_VERSION 으로 덮어쓴다.
TF_DEFAULT_PLAYWRIGHT_VERSION="1.64.1"

tf_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

# 프로젝트 .gitignore 에 .testflow/ 를 한 번만 추가한다. git 저장소가 아니면 건너뛴다.
tf_ensure_gitignore() {
  local root="$1"
  git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  local gi="$root/.gitignore"
  if [ -f "$gi" ] && grep -qxF '.testflow/' "$gi"; then
    return 0
  fi
  if [ -s "$gi" ] && [ -n "$(tail -c1 "$gi")" ]; then
    printf '\n' >> "$gi"
  fi
  printf '# testflow (hbrness) — 스크린샷·임시 파일\n.testflow/\n' >> "$gi"
  echo "GITIGNORE=appended"
}

# 프로젝트(또는 그 하위 디렉토리)에 설치된 Playwright 버전. 없으면 빈 문자열.
tf_project_playwright_version() {
  local dir="$1"
  command -v node >/dev/null 2>&1 || return 0
  (cd "$dir" && node -e '
    for (const p of ["@playwright/test/package.json", "playwright/package.json"]) {
      try { console.log(require(require.resolve(p, { paths: [process.cwd()] })).version); process.exit(0); } catch {}
    }' 2>/dev/null) || true
}

# PNG 헤더에서 가로x세로를 읽는다.
tf_png_size() {
  python3 - "$1" <<'PY' 2>/dev/null || true
import struct, sys
with open(sys.argv[1], "rb") as f:
    head = f.read(24)
if head[:8] == b"\x89PNG\r\n\x1a\n":
    w, h = struct.unpack(">II", head[16:24])
    print(f"{w}x{h}")
PY
}
