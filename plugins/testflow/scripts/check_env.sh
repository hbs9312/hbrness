#!/usr/bin/env bash
# testflow check_env — UI 확인 전에 도구와 설정을 점검한다. 아무것도 바꾸지 않는다.
#
# Usage: check_env.sh [--dir <path>]
#
# 출력 (KEY=VALUE, 한 줄에 하나):
#   ROOT, OS, ARCH, NODE, PROJECT_PLAYWRIGHT, BROWSER_CACHE, DOCKER, DOCKER_ARCH, FONTS_KO,
#   GITIGNORE_TESTFLOW, MCP_PLAYWRIGHT (설정마다 한 줄), WARN (여러 줄 가능)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$SCRIPT_DIR/lib.sh"

DIR="$PWD"
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR=unknown option $1"; exit 2 ;;
  esac
done

ROOT="$(cd "$DIR" && tf_root)"
echo "ROOT=$ROOT"
echo "OS=$(uname -s | tr '[:upper:]' '[:lower:]')"
echo "ARCH=$(uname -m)"

if command -v node >/dev/null 2>&1; then
  echo "NODE=$(node --version)"
else
  echo "NODE=missing"
  echo "WARN=node 가 없습니다. Playwright 를 쓰려면 Node.js 18 이상이 필요합니다."
fi

pw="$(tf_project_playwright_version "$DIR")"
[ -n "$pw" ] || pw="$(tf_project_playwright_version "$ROOT")"
echo "PROJECT_PLAYWRIGHT=${pw:-none}"

# Playwright 브라우저 캐시. 비어 있으면 첫 캡처 때 설치가 필요하다.
cache="${PLAYWRIGHT_BROWSERS_PATH:-}"
if [ -z "$cache" ]; then
  case "$(uname -s)" in
    Darwin) cache="$HOME/Library/Caches/ms-playwright" ;;
    *) cache="$HOME/.cache/ms-playwright" ;;
  esac
fi
if [ -d "$cache" ]; then
  list="$(ls "$cache" 2>/dev/null | grep -E '^(chromium|chromium_headless_shell|webkit|firefox)-' | tr '\n' ' ' | sed 's/ $//')"
  echo "BROWSER_CACHE=${list:-empty}"
else
  echo "BROWSER_CACHE=empty"
fi

if command -v docker >/dev/null 2>&1; then
  if darch="$(docker info --format '{{.Architecture}}' 2>/dev/null)" && [ -n "$darch" ]; then
    echo "DOCKER=running"
    echo "DOCKER_ARCH=$darch"
  else
    echo "DOCKER=not-running"
  fi
else
  echo "DOCKER=missing"
fi

# 한글 폰트. Linux(컨테이너·CI)에서만 의미가 있다. macOS 는 시스템 폰트가 있다.
if [ "$(uname -s)" = "Linux" ]; then
  if command -v fc-list >/dev/null 2>&1 && [ -n "$(fc-list :lang=ko 2>/dev/null | head -1)" ]; then
    echo "FONTS_KO=yes"
  else
    echo "FONTS_KO=no"
    echo "WARN=한글 폰트가 없습니다. 한글이 □ 로 나오면 fonts-noto-cjk 를 설치하세요."
  fi
else
  echo "FONTS_KO=n/a"
fi

if [ -f "$ROOT/.gitignore" ] && grep -qxF '.testflow/' "$ROOT/.gitignore"; then
  echo "GITIGNORE_TESTFLOW=yes"
else
  echo "GITIGNORE_TESTFLOW=no"
fi

# Playwright MCP 설정: 프로젝트 .mcp.json, Claude Code(~/.claude.json 의 user·local scope), Codex(config.toml).
# 서버 인자만 본다. env 값은 읽지도 출력하지도 않는다.
python3 - "$ROOT" <<'PY'
import json, os, re, sys

root = sys.argv[1]
found = []

def classify(scope, name, cfg):
    cmd = str(cfg.get("command", ""))
    args = [str(a) for a in cfg.get("args", []) or []]
    joined = " ".join([cmd] + args)
    url = cfg.get("url") or cfg.get("serverUrl")
    is_pw = "@playwright/mcp" in joined or "playwright/mcp" in joined or "playwright" in name.lower()
    if not is_pw:
        return
    if url and not args:
        found.append((scope, name, "remote", "unknown"))
        return
    if "mcr.microsoft.com/playwright/mcp" in joined:
        headless = "headless"  # Docker 이미지는 headless chromium 만 지원한다
    else:
        headless = "headless" if "--headless" in args else "HEADED"
    isolated = "isolated" if "--isolated" in args else "persistent"
    found.append((scope, name, headless, isolated))

def scan(scope, servers):
    if isinstance(servers, dict):
        for name, cfg in servers.items():
            if isinstance(cfg, dict):
                classify(scope, name, cfg)

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

proj = load_json(os.path.join(root, ".mcp.json"))
if proj:
    scan("project:.mcp.json", proj.get("mcpServers"))

claude = load_json(os.path.expanduser("~/.claude.json"))
if claude:
    scan("claude:user", claude.get("mcpServers"))
    projects = claude.get("projects") or {}
    entry = projects.get(root) or projects.get(os.path.realpath(root))
    if isinstance(entry, dict):
        scan("claude:local", entry.get("mcpServers"))

codex_path = os.path.expanduser("~/.codex/config.toml")
if os.path.exists(codex_path):
    try:
        import tomllib
        with open(codex_path, "rb") as f:
            scan("codex", (tomllib.load(f) or {}).get("mcp_servers"))
    except ModuleNotFoundError:
        # Python 3.10 이하: [mcp_servers.<name>] 블록의 args 만 대충 읽는다
        text = open(codex_path).read()
        for m in re.finditer(r"^\[mcp_servers\.([^\]\s.]+)\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S):
            body = m.group(2)
            cmd = re.search(r'^command\s*=\s*"([^"]*)"', body, re.M)
            args = re.search(r"^args\s*=\s*\[(.*?)\]", body, re.M | re.S)
            classify("codex", m.group(1), {
                "command": cmd.group(1) if cmd else "",
                "args": re.findall(r'"([^"]*)"', args.group(1)) if args else [],
            })
    except Exception:
        pass

if not found:
    print("MCP_PLAYWRIGHT=none")
for scope, name, headless, isolated in found:
    print(f"MCP_PLAYWRIGHT={scope}:{name}:{headless}:{isolated}")
    if headless == "HEADED":
        print(f"WARN={scope} 의 '{name}' 서버에 --headless 가 없습니다. 쓰면 사용자 화면에 브라우저 창이 뜹니다.")
PY
