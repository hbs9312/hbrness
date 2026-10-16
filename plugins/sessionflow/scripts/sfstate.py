#!/usr/bin/env python3
"""sfstate — sessionflow 의 followup / handoff 를 '경로'가 아닌 '저장소' 기준으로 저장하고,
Terraform backend 처럼 원격 key-value 저장소(backend)로 여러 PC 사이에 동기화한다.

$HBRNESS_HOME/backend.json 이 backend 를 정한다 (sfbackend.py). 없으면 이 PC 에만 저장한다.
  local   디렉토리 하나를 원격처럼 쓴다 (테스트·오프라인용)
  s3      S3 API 저장소 (AWS S3·R2·MinIO 등). 자격증명은 macOS Keychain / Linux secret-tool / 
          $HBRNESS_HOME/credentials.json (mode 600) 중 init 이 고른 곳 (--credentials-store).
새 저장소는 age 로 암호화한다 — 푸는 키는 $HBRNESS_HOME/age.key (mode 600, PC 마다 한 번 복사).

저장 위치 ($HBRNESS_STATE_DIR, 기본 ~/.hbrness/state — 원격의 로컬 캐시):

  <repo-key>/followups/<slug>.md      항목 파일. frontmatter 가 진실원이다.
  <repo-key>/followups/INDEX.md       항목 frontmatter 에서 생성한다 (올리지 않는다).
  <repo-key>/followups/_config.json   선택: {"resolved_keep": 10}
  <repo-key>/handoffs/<branch>.md     브랜치별 핸드오프.
  _local/<path-key>/...               remote 가 없는 프로젝트 (동기화 안 함).
  _conflicts/...                      충돌 때 비켜 둔 이 PC 의 버전 (동기화 안 함).
  .sfstate/manifest.json              파일마다 마지막으로 맞춘 원격 etag 와 내용 해시.

<repo-key> 는 프로젝트의 origin remote URL 을 정규화한 값이다 (예: github.com/hbs9312/hbrness).
clone 경로가 PC 마다 달라도 같은 저장소면 같은 키가 나온다.

phase-run / phase-loop / relay 의 오케스트레이션 상태(HANDOFF.md 포함)는 tmux pane 에 묶인
PC 로컬 상태라 여기서 다루지 않는다 — 계속 ~/.hbrness/sessionflow/<path-key>/ 에 있다.

서브커맨드:
  paths       [--dir D]               경로를 KEY=VALUE 로 출력
  prepare     [--dir D]               pull → 레거시 마이그레이션 → INDEX 생성 → paths
  pull        [--dir D] [--background] 원격에서 바뀐 것만 받는다 (실패해도 exit 0).
                                      --dir: 그 프로젝트의 INDEX 도 다시 만든다.
                                      --background: 바로 돌아오고 뒤에서 돈다 (turn 종료 hook 용).
                                      이미 pull 이 돌고 있으면 건너뛴다. 끝나면 PULL_STAMP 를 갱신한다.
  index       [--dir D] [--prune] [--json]
                                      INDEX.md 를 다시 만든다 (--prune: 오래된 resolved 삭제,
                                      --json: 개수와 INDEX 순서의 항목 목록을 JSON 으로 출력)
                                      open·pending·idea 는 우선순위(P0~P3, frontmatter priority —
                                      없으면 P2) → 먼저 추가된 것 → 제목 순이다.
  set-priority [--dir D] <slug> <P0|P1|P2|P3>
                                      항목 frontmatter 의 priority 를 넣거나 바꾸고 INDEX 를 다시 만든다.
                                      올리지는 않는다 (이어서 sync). 없는 항목·잘못된 값은 exit 1.
  sync        [--dir D] [-m MSG]      INDEX 생성·정리 → 이 프로젝트에서 바뀐 파일만 올린다
  status      [--dir D] [--no-pull]   이 저장소의 핸드오프·followup 현황
  migrate     [--dir D] [--dry-run]   이 프로젝트의 경로 기준 레거시 데이터를 옮긴다
  migrate-all [--dry-run]             ~/.hbrness/sessionflow/* 전체를 옮긴다
  init        --backend local --path D
              --backend s3 --bucket B [--endpoint URL] [--prefix P] [--region R]
                           [--path-style | --virtual-host] [--credentials-stdin]
                           [--credentials-store auto|keychain|secret-tool|file]
              [--encrypt | --no-encrypt] [--accept-encryption-change]
                                      backend.json 을 쓰고, 원격과 맞춘 뒤 로컬 전체를 올린다.
                                      예전 git state repo clone 이 있으면 .git 을 옆으로 치우고 내용을 올린다.
                                      새 저장소는 age 로 암호화한다 (age.key 가 없으면 만든다. --no-encrypt 로 끈다).
                                      이미 있는 저장소는 그 설정을 따른다 — 암호화한 저장소면 키를 먼저 복사해 둔다.
                                      같은 저장소를 다시 init 할 때 표시의 암호화 설정이 이 PC 가 쓰던 것과 다르면
                                      멈춘다 (--accept-encryption-change 로 받아들인다).
  doctor                              backend 에 닿는지, conditional write 를 지키는지, 암호화가 되는지 확인한다

환경변수:
  HBRNESS_HOME          기본 ~/.hbrness
  HBRNESS_STATE_DIR     기본 $HBRNESS_HOME/state
  HBRNESS_S3_ACCESS_KEY_ID / HBRNESS_S3_SECRET_ACCESS_KEY / HBRNESS_S3_SESSION_TOKEN
                        s3 자격증명 (credentials.json 보다 먼저)
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sfbackend  # noqa: E402

RESOLVED_KEEP_DEFAULT = 10
MARKER = ".sfstate-migrated.json"

STATUS_ALIASES = {
    "open": "open", "todo": "open",
    "pending": "pending", "decision": "pending", "decisions pending": "pending", "blocked": "pending",
    "idea": "idea", "ideas": "idea",
    "resolved": "resolved", "done": "resolved", "closed": "resolved",
}

# followup 우선순위. 앞이 급하다. frontmatter 에 없거나 모르는 값이면 기본값으로 본다.
PRIORITIES = ("P0", "P1", "P2", "P3")
DEFAULT_PRIORITY = "P2"
PRIORITY_MEANINGS = {
    "P0": "지금 막혀 있거나 바로 해야 한다",
    "P1": "곧 (이번 작업 흐름 안에서)",
    "P2": "보통 — 기본값",
    "P3": "언젠가 / 우선순위 낮음",
}


# ─────────────────────────────────────────────────────────────────────────────
# 공통
# ─────────────────────────────────────────────────────────────────────────────

def hbrness_home() -> Path:
    return Path(os.environ.get("HBRNESS_HOME") or Path.home() / ".hbrness").expanduser()


def state_root() -> Path:
    v = os.environ.get("HBRNESS_STATE_DIR")
    return Path(v).expanduser() if v else hbrness_home() / "state"


def legacy_root() -> Path:
    return hbrness_home() / "sessionflow"


def git(args, cwd, timeout=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 124, "", f"git {args[0]}: {timeout}초 안에 끝나지 않음"
    except (FileNotFoundError, NotADirectoryError) as e:
        return 127, "", str(e)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def now_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def today() -> str:
    return dt.date.today().isoformat()


def tilde(p) -> str:
    s, home = str(p), str(Path.home())
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


@contextlib.contextmanager
def pull_guard():
    """pull 이 이미 돌고 있으면 False 를 준다 — turn 마다 부르는 pull 이 줄지어 쌓이지 않게."""
    home = hbrness_home()
    home.mkdir(parents=True, exist_ok=True)
    with open(home / ".sfstate-pull.lock", "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def pull_stamp() -> Path:
    """pull 이 끝날 때마다 갱신하는 파일. 표시 쪽(statusline mod 등)이 mtime 으로 갱신 시점을 안다."""
    return state_root() / sfbackend.META_DIR / "pulled"


@contextlib.contextmanager
def state_lock():
    """같은 PC 의 여러 세션이 state repo 에 동시에 git 을 돌리지 않게 막는다.
    flock 은 열린 파일마다 걸리므로 한 명령 안에서 중첩해 잡지 않는다."""
    home = hbrness_home()
    home.mkdir(parents=True, exist_ok=True)
    with open(home / ".sfstate.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def normalize_remote(url: str):
    """remote URL → '<host>/<owner>/<repo>' (소문자). 로컬 경로·file:// remote 는 None."""
    url = (url or "").strip()
    if not url:
        return None
    if "://" in url:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme == "file" or not parts.hostname:
            return None
        host, path = parts.hostname, parts.path
    else:
        m = re.match(r"^(?:[^@/]+@)?([^:/]+):(.+)$", url)  # scp 형식: [user@]host:owner/repo
        if not m:
            return None
        host, path = m.group(1), m.group(2)
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    segs = [s for s in path.lower().split("/") if s and s not in (".", "..")]
    if not segs:
        return None
    return "/".join(re.sub(r"[^a-z0-9._-]", "-", s) for s in [host.lower(), *segs])


def valid_branch(name: str) -> bool:
    if not name or name.startswith("/") or name.endswith("/") or ".." in name:
        return False
    if not re.match(r"^[\w./-]+$", name):  # 헤더의 '—', '(none)' 같은 자리표시 거르기
        return False
    return all(seg and seg not in (".", "..") for seg in name.split("/"))


def backend_config_file() -> Path:
    return hbrness_home() / "backend.json"


def load_backend():
    """backend.json 이 없으면 None. 설정이 잘못됐으면 sfbackend.BackendError."""
    return sfbackend.load_backend(backend_config_file())


def backend_status() -> str:
    """none | error | <backend 설명>"""
    try:
        be = load_backend()
    except sfbackend.BackendError:
        return "error"
    return be.describe() if be else "none"


def sync_available() -> bool:
    return backend_config_file().exists()


# ─────────────────────────────────────────────────────────────────────────────
# 프로젝트 컨텍스트
# ─────────────────────────────────────────────────────────────────────────────

class Ctx:
    def __init__(self, cwd=None):
        cwd = Path(cwd or os.getcwd()).expanduser().resolve()
        self.cwd = cwd
        self.is_git = False
        self.branch = None
        self.remote_url = ""
        self.project_root = cwd

        code, common, _ = git(["rev-parse", "--git-common-dir"], cwd)
        if code == 0 and common:
            self.is_git = True
            common_p = (cwd / common).resolve()
            if common_p.name == ".git":
                self.project_root = common_p.parent
            else:  # submodule 등
                c, top, _ = git(["rev-parse", "--show-toplevel"], cwd)
                self.project_root = Path(top).resolve() if c == 0 and top else cwd

            c, br, _ = git(["symbolic-ref", "--short", "-q", "HEAD"], cwd)
            if c == 0 and br:
                self.branch = br
            else:
                c, sha, _ = git(["rev-parse", "--short", "HEAD"], cwd)
                self.branch = f"_detached/{sha}" if c == 0 and sha else "_detached/unborn"

            c, url, _ = git(["config", "--get", "remote.origin.url"], cwd)
            if c != 0 or not url:
                c, remotes, _ = git(["remote"], cwd)
                first = remotes.splitlines()[0] if c == 0 and remotes else ""
                url = git(["config", "--get", f"remote.{first}.url"], cwd)[1] if first else ""
            self.remote_url = url

        self.repo_key = normalize_remote(self.remote_url) if self.is_git else None
        self.legacy_key = str(self.project_root).replace("/", "-")
        root = state_root()
        if self.repo_key:
            self.project_dir = root / self.repo_key
        else:
            self.project_dir = root / "_local" / self.legacy_key.lstrip("-")
        self.followups_dir = self.project_dir / "followups"
        self.index_file = self.followups_dir / "INDEX.md"
        self.handoffs_dir = self.project_dir / "handoffs"
        self.handoff_file = self.handoffs_dir / f"{self.branch or '_nogit'}.md"
        self.legacy_dir = legacy_root() / self.legacy_key

    @property
    def sync(self) -> str:
        return "on" if self.repo_key and sync_available() else "off"

    def sync_reason(self) -> str:
        if not self.repo_key:
            return "remote 가 없는 프로젝트라 이 PC 에만 저장한다"
        if backend_config_file().exists():
            return ""
        if (state_root() / ".git").exists():
            return ("git state repo 동기화는 sessionflow 1.0 에서 없어졌다 — `sfstate.py init --backend s3 …` 로 "
                    "backend 를 정하면 지금 내용이 그대로 올라간다")
        return "backend 가 없다 — `sfstate.py init --backend s3 …` (또는 local) 로 정한다"


def print_paths(ctx: Ctx):
    legacy_single = ctx.followups_dir / "_legacy-FOLLOWUPS.md"
    rows = [
        ("STATE_ROOT", state_root()),
        ("BACKEND", backend_status()),
        ("REPO_KEY", ctx.repo_key or ""),
        ("SYNC", ctx.sync),
        ("PROJECT_ROOT", ctx.project_root),
        ("PROJECT_DIR", ctx.project_dir),
        ("FOLLOWUPS_DIR", ctx.followups_dir),
        ("INDEX_FILE", ctx.index_file),
        ("BRANCH", ctx.branch or ""),
        ("HANDOFFS_DIR", ctx.handoffs_dir),
        ("HANDOFF_FILE", ctx.handoff_file),
        ("MEMORY_KEY", ctx.legacy_key),
        ("LEGACY_DIR", ctx.legacy_dir),
        ("LEGACY_SINGLE", legacy_single if legacy_single.exists() else ""),
        ("PULL_STAMP", pull_stamp()),
    ]
    for k, v in rows:
        print(f"{k}={v}")


# ─────────────────────────────────────────────────────────────────────────────
# frontmatter
# ─────────────────────────────────────────────────────────────────────────────

FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)


def _scalar(v: str) -> str:
    v = v.strip()
    if v.startswith('"'):
        # 닫는 따옴표 뒤에는 주석만 올 수 있다: priority: "P0"  # 급함
        try:
            s, end = json.JSONDecoder().raw_decode(v)
            rest = v[end:].strip()
            if not rest or rest.startswith("#"):
                return str(s)
        except ValueError:
            pass
        return v.strip('"')
    if v.startswith("'"):
        m = re.match(r"'((?:[^']|'')*)'\s*(?:#.*)?$", v)
        if m:
            return m.group(1).replace("''", "'")
    return re.split(r"\s+#", v, maxsplit=1)[0].strip()


def parse_frontmatter(text: str):
    m = FM_RE.match(text)
    if not m:
        return {}, text
    data, key = {}, None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        stripped = line.lstrip()
        if line[:1] in (" ", "\t") or stripped.startswith("- "):
            if key and stripped.startswith("- "):
                if not isinstance(data.get(key), list):
                    data[key] = []
                data[key].append(_scalar(stripped[2:]))
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            key = k.strip()
            data[key] = _scalar(v) if v.strip() else ""
    return data, text[m.end():]


def fm_set(text: str, key: str, value: str) -> str:
    """frontmatter 의 최상위 key 를 넣거나 바꾼다. 나머지 줄은 그대로 둔다."""
    line = f"{key}: {json.dumps(value, ensure_ascii=False)}"
    m = FM_RE.match(text)
    if not m:
        return f"---\n{line}\n---\n\n{text}"
    lines = m.group(1).splitlines()
    for i, l in enumerate(lines):
        if re.match(rf"^{re.escape(key)}\s*:", l):
            lines[i] = line
            break
    else:
        # summary 는 title 바로 아래, priority 는 status 바로 아래, 나머지는 끝에 둔다
        at = len(lines)
        after = {"summary": "title", "priority": "status"}.get(key)
        if after:
            at = next((i + 1 for i, l in enumerate(lines) if re.match(rf"^{after}\s*:", l)), len(lines))
        lines.insert(at, line)
    return "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]


def first_heading(body: str) -> str:
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else ""


# ─────────────────────────────────────────────────────────────────────────────
# followups INDEX
# ─────────────────────────────────────────────────────────────────────────────

def priority_of(value) -> str:
    """frontmatter 의 priority 를 P0~P3 로 맞춘다. 대소문자는 가리지 않고, 없거나 모르는 값은 기본값."""
    p = str(value or "").strip().upper()
    return p if p in PRIORITIES else DEFAULT_PRIORITY


def load_items(followups_dir: Path):
    items = []
    if not followups_dir.is_dir():
        return items
    for f in sorted(followups_dir.glob("*.md")):
        if f.name == "INDEX.md" or f.name.startswith("_"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, body = parse_frontmatter(text)
        status = STATUS_ALIASES.get(str(fm.get("status", "")).strip().lower(), "open")
        items.append({
            "slug": f.stem,
            "path": f,
            "title": str(fm.get("title") or first_heading(body) or f.stem),
            "status": status,
            "priority": priority_of(fm.get("priority")),
            "discovered": str(fm.get("discovered") or ""),
            "resolved": str(fm.get("resolved") or ""),
            "summary": str(fm.get("summary") or ""),
        })
    return items


def resolved_keep(followups_dir: Path) -> int:
    try:
        cfg = json.loads((followups_dir / "_config.json").read_text(encoding="utf-8"))
        n = int(cfg.get("resolved_keep", RESOLVED_KEEP_DEFAULT))
        return n if n >= 0 else RESOLVED_KEEP_DEFAULT
    except (OSError, ValueError, TypeError, AttributeError):
        return RESOLVED_KEEP_DEFAULT


def _cell(s: str) -> str:
    return s.replace("\n", " ").replace("|", "\\|").strip()


def group_items(items, keep: int):
    """INDEX 에 보이는 순서로 묶는다: open·pending·idea 는 우선순위(P0→P3) → 먼저 추가된 것 → 제목,
    discovered 가 없는 항목은 그 우선순위의 맨 뒤. resolved 는 최근에 해결한 것부터."""
    by = {k: [i for i in items if i["status"] == k] for k in ("open", "pending", "idea", "resolved")}
    for k in ("open", "pending", "idea"):
        by[k].sort(key=lambda i: (PRIORITIES.index(i["priority"]), not i["discovered"], i["discovered"], i["title"]))
    by["resolved"].sort(key=lambda i: (i["resolved"] or i["discovered"], i["title"]), reverse=True)
    return by


def urgent_note(items, levels=("P0", "P1")) -> str:
    """' (P0 1 · P1 2)' — levels 중 항목이 있는 단계만. 하나도 없으면 빈 문자열."""
    parts = [f"{p} {n}" for p in levels if (n := sum(1 for i in items if i["priority"] == p))]
    return f" ({' · '.join(parts)})" if parts else ""


def build_index(ctx: Ctx, prune=False):
    """INDEX.md 를 다시 만든다. prune=True 면 상한을 넘는 오래된 resolved 파일을 지운다.
    반환: (counts dict, 지운 파일 목록)"""
    fdir = ctx.followups_dir
    items = load_items(fdir)
    if not items:
        if ctx.index_file.exists():
            ctx.index_file.unlink()
        return {"open": 0, "pending": 0, "idea": 0, "resolved": 0}, []

    keep = resolved_keep(fdir)
    by = group_items(items, keep)
    pruned = []
    if prune and len(by["resolved"]) > keep:
        for i in by["resolved"][keep:]:
            i["path"].unlink(missing_ok=True)
            pruned.append(i["slug"])
        by["resolved"] = by["resolved"][:keep]
    shown_resolved = by["resolved"][:keep]

    link = lambda i: f"[{i['slug']}.md](./{i['slug']}.md)"
    out = [
        "# Project Followups — Index",
        "",
        f"> Repo: {ctx.repo_key or ctx.project_root}",
        f"> Generated: {now_str()} — sfstate.py 가 항목 frontmatter 로 만든다. 직접 고치지 말고 항목 파일을 고친다.",
        f"> Open: {len(by['open'])}{urgent_note(by['open'])} · Pending: {len(by['pending'])}{urgent_note(by['pending'])}"
        f" · Ideas: {len(by['idea'])} · Resolved: {len(by['resolved'])}",
        "> 우선: " + " · ".join(f"{p} {PRIORITY_MEANINGS[p]}" for p in PRIORITIES),
    ]
    row = lambda i: f"| {i['priority']} | {_cell(i['title'])} | {_cell(i['summary'])} | {i['discovered']} | {link(i)} |"
    if by["open"]:
        out += ["", "## Open", "", "| 우선 | 제목 | 한 줄 설명 | Discovered | 상세 |", "|---|---|---|---|---|"]
        out += [row(i) for i in by["open"]]
    if by["pending"]:
        out += ["", "## Decisions Pending", "", "| 우선 | 주제 | 한 줄 설명 | Discovered | 상세 |", "|---|---|---|---|---|"]
        out += [row(i) for i in by["pending"]]
    if by["idea"]:
        out += ["", "## Ideas / Improvements", ""]
        for i in by["idea"]:
            extra = f" — {_cell(i['summary'])}" if i["summary"] else ""
            out.append(f"- [{i['priority']}] {i['discovered'] or '????-??-??'} {_cell(i['title'])}{extra} ({link(i)})")
    if shown_resolved:
        out += ["", f"## Resolved (최근 {keep})", "", "| 제목 | Resolved | 상세 |", "|---|---|---|"]
        out += [f"| ~~{_cell(i['title'])}~~ | {i['resolved']} | {link(i)} |" for i in shown_resolved]
    fdir.mkdir(parents=True, exist_ok=True)
    ctx.index_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    return {k: len(v) for k, v in by.items()}, pruned


# ─────────────────────────────────────────────────────────────────────────────
# 동기화
# ─────────────────────────────────────────────────────────────────────────────

def _pull():
    """반환: (ok|off|failed, 설명, conflicts[(상대경로, 비켜 둔 경로)])"""
    try:
        be = load_backend()
    except sfbackend.BackendError as e:
        return "failed", str(e), []
    if not be:
        return "off", "backend 없음", []
    try:
        rep = sfbackend.Cache(state_root(), be).pull()
    except sfbackend.PartialSync as e:
        return "failed", str(e), e.report["conflicts"]
    except (sfbackend.BackendError, OSError) as e:
        return "failed", str(e), []
    return "ok", "", rep["conflicts"]


def _sync_backend(ctx: Ctx, be):
    """반환: (pushed|nochange|failed, 설명, conflicts)"""
    rel = ctx.project_dir.relative_to(state_root()).as_posix()
    try:
        rep = sfbackend.Cache(state_root(), be).push(rel)
    except sfbackend.PartialSync as e:
        if e.report["conflicts"] or e.report["got"]:
            build_index(ctx)
        done = len(e.report["put"]) + len(e.report["deleted"])
        return "failed", (f"{e} — {done}개는 반영했고, 못 올린 변경은 로컬에 남아 다음 sync 때 다시 올린다"), \
            e.report["conflicts"]
    except (sfbackend.BackendError, OSError) as e:
        return "failed", f"{e} — 못 올린 변경은 로컬에 남아 다음 sync 때 다시 올린다", []
    if rep["conflicts"] or rep["got"]:
        build_index(ctx)  # 원격본을 받아 왔으면 INDEX 도 다시 만든다
    st = "pushed" if rep["put"] or rep["deleted"] else "nochange"
    detail = ""
    if rep["got"]:
        detail = "지우려던 파일을 다른 PC 가 고쳐서 지우지 않고 받아 왔다: " + ", ".join(rep["got"])
    return st, detail, rep["conflicts"]


def _sync(ctx: Ctx, message: str):
    """반환: (pushed|nochange|local-only|failed, 설명, pruned, conflicts). message 는 지금은 쓰지 않는다."""
    _, pruned = build_index(ctx, prune=True)
    if ctx.sync != "on":
        return "local-only", ctx.sync_reason(), pruned, []
    try:
        be = load_backend()
    except sfbackend.BackendError as e:
        return "failed", str(e), pruned, []
    st, detail, conflicts = _sync_backend(ctx, be)
    return st, detail, pruned, conflicts


def print_conflicts(conflicts):
    for rel, aside in conflicts:
        print(f"CONFLICT={rel} → {tilde(aside)}")


# ─────────────────────────────────────────────────────────────────────────────
# 레거시(경로 기준) 마이그레이션
# ─────────────────────────────────────────────────────────────────────────────

def _split_row(line: str):
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.strip() for c in cells[1:-1]] if len(cells) >= 3 else []


def parse_legacy_index(path: Path):
    """레거시 INDEX.md → (slug→{title,summary,date,section}, ideas[(date,text)], resolved_keep|None)"""
    meta, ideas, keep = {}, [], None
    if not path.exists():
        return meta, ideas, keep
    section = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        h = re.match(r"^##\s+(.+)$", line)
        if h:
            title = h.group(1).lower()
            section = ("open" if title.startswith("open") else
                       "pending" if "pending" in title or "decision" in title else
                       "idea" if title.startswith("idea") else
                       "resolved" if title.startswith("resolved") else "")
            m = re.search(r"최근\s*(\d+)", h.group(1))
            if section == "resolved" and m:
                keep = int(m.group(1))
            continue
        if section == "idea":
            m = re.match(r"^\s*[-*]\s+(?:(\d{4}-\d{2}-\d{2})\s+)?(.+)$", line)
            if m:
                ideas.append((m.group(1) or "", m.group(2).strip()))
            continue
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = _split_row(line)
        lm = re.search(r"\(\./([^)]+?)\.md\)", line)
        if not cells or not lm:
            continue
        slug = lm.group(1)
        if section in ("open", "pending") and len(cells) >= 4:
            meta[slug] = {"title": cells[0], "summary": cells[1].replace("\\|", "|"),
                          "date": cells[2], "section": section}
        elif section == "resolved" and len(cells) >= 3:
            meta[slug] = {"title": cells[0].strip("~"), "summary": "", "date": cells[1], "section": "resolved"}
    return meta, ideas, keep


def _idea_slug(text: str, date: str, taken: set) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    base = "-".join(words[:5]) if len("".join(words)) >= 6 else ""
    if not base:
        base = f"idea-{date or 'undated'}-{hashlib.sha1(text.encode()).hexdigest()[:6]}"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    taken.add(slug)
    return slug


def _handoff_branch(text: str):
    m = re.search(r"^>\s*Branch:\s*`?([^`\s]+)`?", text, re.M)
    return m.group(1).strip() if m else None


def _worktree_branch(project_root: Path, wt: str):
    head = project_root / ".git" / "worktrees" / wt / "HEAD"
    if not head.exists():
        return None, False
    m = re.match(r"^ref:\s*refs/heads/(.+)$", head.read_text().strip())
    return (m.group(1) if m else None), True


def migrate_ctx(ctx: Ctx, legacy_dir: Path | None = None, dry_run=False):
    legacy = legacy_dir or ctx.legacy_dir
    rep = {"legacy": str(legacy), "target": str(ctx.project_dir), "repo_key": ctx.repo_key or "",
           "followups": 0, "ideas": 0, "handoffs": [], "skipped": []}
    if not legacy.is_dir():
        rep["status"] = "none"
        return rep
    if (legacy / MARKER).exists():
        rep["status"] = "done-before"
        return rep

    # followups
    src = legacy / "followups"
    if src.is_dir():
        meta, ideas, keep = parse_legacy_index(src / "INDEX.md")
        taken = {p.stem for p in ctx.followups_dir.glob("*.md")} if ctx.followups_dir.is_dir() else set()
        for f in sorted(src.glob("*.md")):
            if f.name == "INDEX.md":
                continue
            dst = ctx.followups_dir / f.name
            if dst.exists():
                rep["skipped"].append(f"followups/{f.name}: 이미 있음")
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            fm, body = parse_frontmatter(text)
            info = meta.get(f.stem, {})
            if not fm:
                text = fm_set(text, "title", info.get("title") or first_heading(body) or f.stem)
                text = fm_set(text, "status", info.get("section") or "open")
                if info.get("date"):
                    text = fm_set(text, "discovered" if info.get("section") != "resolved" else "resolved",
                                  info["date"])
            if not fm.get("summary") and info.get("summary"):
                text = fm_set(text, "summary", info["summary"])
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(text, encoding="utf-8")
            taken.add(f.stem)
            rep["followups"] += 1
        for date, idea in ideas:
            slug = _idea_slug(idea, date, taken)
            text = (f"---\ntitle: {json.dumps(idea, ensure_ascii=False)}\nstatus: idea\n"
                    f"discovered: {date}\n---\n\n# {idea}\n")
            if not dry_run:
                ctx.followups_dir.mkdir(parents=True, exist_ok=True)
                (ctx.followups_dir / f"{slug}.md").write_text(text, encoding="utf-8")
            rep["ideas"] += 1
        if keep is not None and keep != RESOLVED_KEEP_DEFAULT and not dry_run:
            cfg = ctx.followups_dir / "_config.json"
            if not cfg.exists():
                ctx.followups_dir.mkdir(parents=True, exist_ok=True)
                cfg.write_text(json.dumps({"resolved_keep": keep}) + "\n", encoding="utf-8")
    elif (legacy / "FOLLOWUPS.md").exists():
        # 더 오래된 단일 파일 형식 — 항목 분해는 followup 스킬(LLM)이 한다.
        if not dry_run:
            ctx.followups_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy / "FOLLOWUPS.md", ctx.followups_dir / "_legacy-FOLLOWUPS.md")
        rep["skipped"].append("FOLLOWUPS.md: _legacy-FOLLOWUPS.md 로 복사 — followup 스킬이 항목으로 나눈다")

    # handoffs — 메인 + 아직 살아 있는 워크트리만. 지워진 워크트리의 핸드오프는 옮기지 않는다.
    candidates = []
    if (legacy / "HANDOFF.md").exists():
        candidates.append(("main", legacy / "HANDOFF.md"))
    wt_root = legacy / "worktrees"
    if wt_root.is_dir():
        for d in sorted(wt_root.iterdir()):
            if (d / "HANDOFF.md").exists():
                candidates.append((d.name, d / "HANDOFF.md"))
    for name, path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        branch = _handoff_branch(text) if ctx.is_git else "_nogit"
        if name != "main":
            wt_branch, alive = _worktree_branch(ctx.project_root, name)
            if not alive:
                rep["skipped"].append(f"worktrees/{name}/HANDOFF.md: 워크트리가 없어 건너뜀")
                continue
            branch = branch or wt_branch
        elif not branch and ctx.is_git:
            branch = git(["symbolic-ref", "--short", "-q", "HEAD"], ctx.project_root)[1] or None
        if not branch or not valid_branch(branch):
            rep["skipped"].append(f"{name} HANDOFF.md: 브랜치를 알 수 없음")
            continue
        dst = ctx.handoffs_dir / f"{branch}.md"
        if dst.exists() or branch in [h for h, _ in rep["handoffs"]]:
            rep["skipped"].append(f"{name} HANDOFF.md: {branch} 핸드오프가 이미 있음")
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
        rep["handoffs"].append((branch, name))

    if not dry_run:
        (legacy / MARKER).write_text(json.dumps({
            "repo_key": ctx.repo_key, "project_dir": str(ctx.project_dir), "migrated_at": now_str(),
            "host": socket.gethostname(), "followups": rep["followups"], "ideas": rep["ideas"],
            "handoffs": rep["handoffs"],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rep["status"] = "migrated" if not dry_run else "dry-run"
    return rep


def resolve_legacy_key(key: str):
    """'-Users-seok-development-my-app' 같은 경로 키를 실제 디렉토리로 되돌린다.
    '/'→'-' 변환은 손실이 있어 디스크를 실제로 걸어 보며 찾는다."""
    if not key.startswith("-"):
        return None
    tokens = key[1:].split("-")

    def walk(base: Path, i: int):
        if i == len(tokens):
            return base
        for j in range(len(tokens), i, -1):
            name = "-".join(tokens[i:j])
            if name and (base / name).is_dir():
                found = walk(base / name, j)
                if found:
                    return found
        return None

    return walk(Path("/"), 0)


def legacy_path_hint(legacy: Path):
    """레거시 파일 헤더에 적힌 원래 경로 (INDEX 의 Project:, HANDOFF 의 Working Directory:)."""
    for f, pat in ((legacy / "followups" / "INDEX.md", r"^>\s*Project:\s*(\S.*)$"),
                   (legacy / "HANDOFF.md", r"^>\s*Working Directory:\s*(\S.*)$")):
        if f.exists():
            m = re.search(pat, f.read_text(encoding="utf-8", errors="replace"), re.M)
            if m:
                p = Path(m.group(1).strip().strip("`")).expanduser()
                if p.is_dir() and str(p).replace("/", "-") == legacy.name:
                    return p
    return None


def print_migrate_report(rep: dict, label: str):
    st = rep["status"]
    if st in ("none", "done-before"):
        print(f"MIGRATE={st}" if not label else f"- {label}: {st}")
        return
    hs = ", ".join(f"{b}←{n}" for b, n in rep["handoffs"]) or "없음"
    head = f"- {label}: " if label else "MIGRATE="
    print(f"{head}{st} → {rep['repo_key'] or tilde(rep['target'])} "
          f"(followup {rep['followups']} · idea {rep['ideas']} · handoff {hs})")
    for s in rep["skipped"]:
        print(f"    건너뜀: {s}")


# ─────────────────────────────────────────────────────────────────────────────
# 명령
# ─────────────────────────────────────────────────────────────────────────────

def cmd_paths(a):
    print_paths(Ctx(a.dir))


def cmd_prepare(a):
    ctx = Ctx(a.dir)
    with state_lock():
        st, detail, conflicts = _pull()
        print(f"PULL={st}" + (f" ({detail})" if detail else ""))
        print_conflicts(conflicts)
        rep = migrate_ctx(ctx)
        print_migrate_report(rep, "")
        if rep["status"] == "migrated":
            st, detail, _, conflicts = _sync(ctx, "migrate path-keyed state")
            print(f"MIGRATE_SYNC={st}" + (f" ({detail})" if detail else ""))
            print_conflicts(conflicts)
        else:
            build_index(ctx)
    if ctx.sync != "on":
        print(f"SYNC_NOTE={ctx.sync_reason()}")
    print_paths(ctx)


def cmd_pull(a):
    if a.background:
        if not sync_available():
            return
        target = str(Path(a.dir or os.getcwd()).expanduser().resolve())
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "pull", "--dir", target],
                         cwd=target if os.path.isdir(target) else None,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return
    with pull_guard() as acquired:
        if not acquired:
            print("PULL=skipped (이미 진행 중)")
            return
        with state_lock():
            st, detail, conflicts = _pull()
            if a.dir:
                build_index(Ctx(a.dir))
            if st != "off":
                stamp = pull_stamp()
                stamp.parent.mkdir(parents=True, exist_ok=True)
                stamp.touch()
    print(f"PULL={st}" + (f" ({detail})" if detail else ""))
    print_conflicts(conflicts)


def cmd_index(a):
    ctx = Ctx(a.dir)
    counts, pruned = build_index(ctx, prune=a.prune)
    if a.json:
        keep = resolved_keep(ctx.followups_dir)
        by = group_items(load_items(ctx.followups_dir), keep)
        fields = ("slug", "title", "summary", "status", "priority", "discovered", "resolved")
        print(json.dumps({
            "index": str(ctx.index_file) if any(counts.values()) else "",
            "counts": counts,
            "resolved_keep": keep,
            "items": [{f: i[f] for f in fields}
                      for k in ("open", "pending", "idea", "resolved")
                      for i in (by[k][:keep] if k == "resolved" else by[k])],
            "pruned": pruned,
        }, ensure_ascii=False))
        return
    print(f"INDEX={ctx.index_file if any(counts.values()) else '(항목 없음)'}")
    print("COUNTS=" + " ".join(f"{k}:{v}" for k, v in counts.items()))
    if pruned:
        print("PRUNED=" + ",".join(pruned))


def cmd_set_priority(a):
    ctx = Ctx(a.dir)
    value = str(a.priority).strip().upper()
    if value not in PRIORITIES:
        print(f"set-priority: 우선순위는 {'|'.join(PRIORITIES)} 중 하나다: {a.priority}", file=sys.stderr)
        sys.exit(1)
    slug = a.slug[:-3] if a.slug.endswith(".md") else a.slug
    path = ctx.followups_dir / f"{slug}.md"
    if not slug or "/" in slug or "\\" in slug or slug[0] in "._" or slug == "INDEX" or not path.is_file():
        print(f"set-priority: 항목이 없다: {a.slug} ({tilde(ctx.followups_dir)})", file=sys.stderr)
        sys.exit(1)
    with state_lock():
        text = path.read_text(encoding="utf-8")
        before = priority_of(parse_frontmatter(text)[0].get("priority"))
        changed = fm_set(text, "priority", value)
        if changed != text:
            path.write_text(changed, encoding="utf-8")
        build_index(ctx)
    print(f"PRIORITY={value}")
    print(f"PREVIOUS={before}")
    print(f"ITEM={path}")


def cmd_sync(a):
    ctx = Ctx(a.dir)
    with state_lock():
        st, detail, pruned, conflicts = _sync(ctx, a.message)
    print(f"SYNC={st}" + (f" ({detail})" if detail else ""))
    print_conflicts(conflicts)
    if pruned:
        print("PRUNED=" + ",".join(pruned))


def _when(path: Path, cache=None) -> str:
    """핸드오프 헤더의 Generated 를 먼저 쓴다 — 파일 시각은 옮기거나 다시 받은 시각일 수 있다."""
    try:
        m = re.search(r"^>\s*Generated:\s*(.+)$", path.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    mtime = dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    if cache is not None and cache.synced(path.relative_to(state_root()).as_posix()):
        return mtime
    return mtime + " (미동기화)"


def cmd_status(a):
    ctx = Ctx(a.dir)
    if not a.no_pull:
        with state_lock():
            st, detail, conflicts = _pull()
            build_index(ctx)
        print(f"pull: {st}" + (f" ({detail})" if detail else ""))
        for rel, aside in conflicts:
            print(f"  충돌: {rel} — 이 PC 의 버전은 {tilde(aside)} 에 남겼다")
    print(f"repo: {ctx.repo_key or tilde(ctx.project_root) + ' (remote 없음)'} · sync {ctx.sync}")
    if ctx.sync != "on":
        print(f"  {ctx.sync_reason()}")
    try:
        be = load_backend()
    except sfbackend.BackendError:
        be = None
    try:
        cache = sfbackend.Cache(state_root(), be) if be and ctx.repo_key else None
    except (sfbackend.BackendError, OSError):
        cache = None
    if ctx.handoff_file.exists():
        print(f"handoff [{ctx.branch}]: {tilde(ctx.handoff_file)} ({_when(ctx.handoff_file, cache)})")
    else:
        print(f"handoff [{ctx.branch or '-'}]: 없음")
    others = []
    if ctx.handoffs_dir.is_dir():
        for f in sorted(ctx.handoffs_dir.rglob("*.md")):
            if f != ctx.handoff_file:
                others.append(f"{f.relative_to(ctx.handoffs_dir).with_suffix('')} ({_when(f, cache)})")
    if others:
        print("다른 브랜치 핸드오프: " + ", ".join(others))
    items = load_items(ctx.followups_dir)
    if items:
        g = {k: [i for i in items if i["status"] == k] for k in ("open", "pending", "idea", "resolved")}
        print(f"followups: open {len(g['open'])}{urgent_note(g['open'], ('P0',))} · "
              f"pending {len(g['pending'])}{urgent_note(g['pending'], ('P0',))} · idea {len(g['idea'])} · "
              f"resolved {len(g['resolved'])} → {tilde(ctx.index_file)}")
    else:
        print("followups: 없음")


def cmd_migrate(a):
    ctx = Ctx(a.dir)
    with state_lock():
        rep = migrate_ctx(ctx, dry_run=a.dry_run)
        if rep["status"] == "migrated":
            build_index(ctx)
            st, detail, _, conflicts = _sync(ctx, "migrate path-keyed state")
            rep["sync"] = st + (f" ({detail})" if detail else "")
    print_migrate_report(rep, "")
    if rep.get("sync"):
        print(f"SYNC={rep['sync']}")
        print_conflicts(conflicts)


def cmd_migrate_all(a):
    root = legacy_root()
    if not root.is_dir():
        print(f"{tilde(root)} 가 없다 — 옮길 것이 없음")
        return
    with state_lock():
        if not a.dry_run:
            st, detail, conflicts = _pull()
            print(f"PULL={st}" + (f" ({detail})" if detail else ""))
            print_conflicts(conflicts)
        touched = []
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            if not (d / "followups").is_dir() and not (d / "HANDOFF.md").exists() \
                    and not (d / "worktrees").is_dir() and not (d / "FOLLOWUPS.md").exists():
                continue
            path = legacy_path_hint(d) or resolve_legacy_key(d.name)
            if not path:
                print(f"- {d.name}: 원래 경로를 찾지 못해 건너뜀")
                continue
            ctx = Ctx(path)
            rep = migrate_ctx(ctx, legacy_dir=d, dry_run=a.dry_run)
            print_migrate_report(rep, f"{d.name} ({tilde(path)})")
            if rep["status"] == "migrated":
                build_index(ctx)
                touched.append(ctx)
        if touched and not a.dry_run:
            results = [_sync(ctx, "migrate path-keyed state") for ctx in touched]
            print("SYNC=" + ", ".join(sorted({r[0] for r in results})))
            for r in results:
                if r[1]:
                    print(f"    {r[0]}: {r[1]}")
                print_conflicts(r[3])


def _archive_git_clone(root: Path):
    """예전 git state repo clone 이면 .git·.gitignore·README.md 를 옆 디렉토리로 치운다.
    항목 파일은 그대로 두고 init 이 backend 로 올린다. 반환: 옮긴 디렉토리 또는 None."""
    if not (root / ".git").exists():
        return None
    dst = root.with_name(f"{root.name}.git-archive-{dt.datetime.now():%Y%m%d%H%M%S}")
    dst.mkdir(parents=True)
    for name in (".git", ".gitignore", "README.md"):
        if os.path.lexists(root / name):
            os.replace(root / name, dst / name)
    return dst


def _read_credentials_stdin() -> dict:
    """stdin 으로 자격증명을 받는다 — 명령줄·shell history 에 남기지 않으려고.
    JSON 객체 또는 두 줄(access key id, secret access key[, session token])."""
    text = sys.stdin.read().strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError as e:
            raise sfbackend.BackendError(f"stdin 자격증명 JSON 을 읽지 못했다: {e}")
        return {k: str(v) for k, v in data.items() if k in ("access_key_id", "secret_access_key", "session_token") and v}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        raise sfbackend.BackendError("stdin 에 access key id 와 secret access key 를 한 줄씩 넣는다")
    creds = {"access_key_id": lines[0], "secret_access_key": lines[1]}
    if len(lines) > 2:
        creds["session_token"] = lines[2]
    return creds


def _init_config(a):
    """반환: (cfg, backend, 저장할 자격증명 또는 None)"""
    if a.backend == "local":
        if not a.path:
            raise sfbackend.BackendError("--backend local 에는 --path <dir> 가 필요하다")
        cfg = {"type": "local", "path": str(Path(a.path).expanduser().resolve())}
        return cfg, sfbackend.make_backend(cfg, key_path=key_file()), None
    if not a.bucket:
        raise sfbackend.BackendError("--backend s3 에는 --bucket 이 필요하다")
    cfg = {"type": "s3", "bucket": a.bucket}
    for k in ("endpoint", "prefix", "region"):
        if getattr(a, k):
            cfg[k] = getattr(a, k)
    if a.path_style is not None:
        cfg["path_style"] = a.path_style
    # stdin 으로 받은 자격증명은 예전 것을 통째로 바꾼다 — 예전 session_token 이 섞이면 서명이 틀린다
    new_creds = _read_credentials_stdin() if a.credentials_stdin else None
    env = sfbackend.env_credentials()
    if new_creds and env:
        print("init: HBRNESS_S3_* 환경변수가 있으면 credentials.json 보다 그쪽을 먼저 쓴다 — "
              "stdin 자격증명은 저장만 하고 지금은 환경변수로 맞춘다", file=sys.stderr)
    # 이후 명령(load_backend)과 같은 순서로 고른다: 환경변수 묶음 → stdin(곧 저장될 값) → 저장된 값
    creds = env or new_creds or sfbackend.load_credentials(creds_file(), previous_credentials_store())
    be = sfbackend.S3Backend(cfg, creds)
    be.key_path = key_file()
    return cfg, be, new_creds


def creds_file() -> Path:
    return sfbackend.credentials_file(backend_config_file())


def previous_credentials_store() -> str:
    try:
        prev = sfbackend.load_config(backend_config_file()) or {}
    except sfbackend.BackendError:
        prev = {}
    return prev.get("credentials") or "file"


def _init_credentials(a, cfg, new_creds):
    """s3 자격증명을 둘 곳을 정하고(auto 면 이 PC 에 맞게), 새로 받았거나 둘 곳이 바뀌었으면 거기에 저장한다.
    반환: 둔 곳 (local backend 면 None)."""
    if cfg["type"] != "s3":
        return None
    store = a.credentials_store if a.credentials_store != "auto" else sfbackend.auto_credentials_store()
    prev = previous_credentials_store()
    creds = new_creds
    if not creds and store != prev:  # 저장된 것을 새 자리로 옮긴다
        creds = sfbackend.stored_credentials(creds_file(), prev)
    if creds:
        sfbackend.save_credentials(store, creds_file(), creds)
        if store != prev and prev != "file":  # 예전 자리(Keychain 등)에 남은 것을 치운다
            try:
                sfbackend.forget_credentials(prev, creds_file())
            except sfbackend.BackendError as e:
                print(f"CREDENTIALS_WARN={e} — 새 자리({store})로는 옮겼다. 예전 자리에 남은 비밀값은 직접 지운다")
    cfg["credentials"] = store
    return store


def _same_place(prev, cfg) -> bool:
    """예전 backend.json 이 같은 저장소 자리를 가리키나. backend 가 실제로 쓰는 주소(location)로 비교한다."""
    if not isinstance(prev, dict):
        return False
    try:
        return sfbackend.location(prev) == sfbackend.location(cfg)
    except sfbackend.BackendError:
        return False


def _init_encryption(a, cfg, be):
    """저장소의 암호화를 정한다. 새 저장소는 기본으로 age 로 암호화하고(키가 없으면 만든다), 이미 있는 저장소는
    그 설정을 따른다. 같은 저장소를 다시 init 하면 이 PC 가 backend.json 에 적어 둔 설정과 먼저 맞춰 본다 —
    누가 표시를 고쳐 암호화를 빼거나 공개키를 더해도 다시 init 한 번으로 받아들이지 않게.
    반환: (encryption 설정 또는 None, 새로 만든 키 경로 또는 None)"""
    try:
        prev = sfbackend.load_config(backend_config_file())
    except sfbackend.BackendError:
        prev = None
    prev_enc = (prev.get("encryption") or None) if isinstance(prev, dict) else None
    pinned = prev_enc if _same_place(prev, cfg) else False  # False: 이 PC 가 쓰던 자리가 아니다
    raw = be.read_marker()
    created = None
    if raw is None or not raw.strip():  # 새 저장소
        enc = None
        if a.encrypt is not False:
            created = None if be.key_path.exists() else be.key_path
            enc = {"type": "age", "recipients": [sfbackend.make_key(be.key_path)]}
        declared = be.ensure(enc).get("encryption")
    else:
        declared = sfbackend.parse_marker(raw).get("encryption")
        if a.encrypt and not declared:
            raise sfbackend.BackendError("암호화하지 않고 만든 저장소다 — 암호화하려면 새 bucket 이나 --prefix 로 init 한다")
        if a.encrypt is False and declared:
            raise sfbackend.BackendError("age 로 암호화한 저장소라 --no-encrypt 로 바꿀 수 없다")
        # 자리를 다르게 적어 같은 저장소로 안 보여도: 암호화를 쓰던 PC 가 평문 저장소로 가려면 그렇다고 적어야 한다
        if pinned is False and prev_enc and not declared and a.encrypt is not False \
                and not a.accept_encryption_change:
            raise sfbackend.BackendError("이 PC 는 암호화한 저장소를 쓰고 있었는데 이 저장소는 암호화하지 않았다 — "
                                         "평문 저장소로 옮기는 게 맞으면 --no-encrypt 를 붙인다")
    if pinned is not False and declared != pinned and not a.accept_encryption_change:
        raise sfbackend.BackendError(
            f"저장소 표시의 암호화 설정이 이 PC 가 쓰던 것과 다르다 (이 PC: {describe_encryption(pinned)} → 표시: "
            f"{describe_encryption(declared)}) — 누가 왜 바꿨는지 확인한다. 맞게 바꾼 것이면 --accept-encryption-change 를 붙인다")
    if declared:
        sfbackend.Age(declared, be.key_path).check_key()  # 다른 PC 가 만든 저장소면 그 키를 복사해 왔어야 한다
    be.encryption = declared
    return declared, created


def describe_encryption(enc) -> str:
    return f"age {', '.join(enc['recipients'])}" if enc else "암호화 없음"


def cmd_init(a):
    """backend.json 을 쓰고 원격과 맞춘 뒤 로컬 전체를 올린다. 이미 쓰던 state 디렉토리(예전 git state repo
    clone 포함)가 있으면 그 내용이 그대로 올라간다."""
    try:
        cfg, be, new_creds = _init_config(a)
        enc, created_key = _init_encryption(a, cfg, be)
    except (sfbackend.BackendError, OSError) as e:
        print(f"init: {e}", file=sys.stderr)
        sys.exit(1)
    if enc:
        cfg["encryption"] = enc
    root = state_root()
    with state_lock():
        try:
            store = _init_credentials(a, cfg, new_creds)
        except sfbackend.BackendError as e:
            print(f"init: {e}", file=sys.stderr)
            sys.exit(1)
        sfbackend.save_config(backend_config_file(), cfg)
        root.mkdir(parents=True, exist_ok=True)
        archived = _archive_git_clone(root)
        pulled = None
        try:
            cache = sfbackend.Cache(root, be)
            pulled = cache.pull()
            pushed = cache.push("")
        except (sfbackend.BackendError, OSError) as e:
            print(f"BACKEND={be.describe()}")
            print(f"INIT=failed ({e}) — 다시 init 하면 이어서 맞춘다")
            print_conflicts((pulled["conflicts"] if pulled else [])
                            + (e.report["conflicts"] if isinstance(e, sfbackend.PartialSync) else []))
            sys.exit(1)
    print(f"STATE_ROOT={root}")
    print(f"BACKEND={be.describe()}")
    print(f"ENCRYPTION={encryption_line(enc, be.key_path)}")
    if store:
        print(f"CREDENTIALS={store}")
    if enc and len(enc["recipients"]) > 1:
        print("ENCRYPTION_WARN=공개키가 여럿이다 — init 은 하나만 만든다. 모두 아는 키인지 확인한다 "
              "(모르는 키가 있으면 그 키의 주인도 기록을 풀 수 있다)")
    if created_key:
        print(f"AGE_KEY_CREATED={tilde(created_key)} — 다른 PC 에는 이 파일을 같은 자리에 복사한다 (mode 600). "
              "잃으면 올린 기록을 아무도 풀 수 없으니 따로 보관해 둔다")
    if archived:
        print(f"GIT_ARCHIVE={archived} (예전 state repo 의 .git — 확인 뒤 지워도 된다)")
    print(f"PULL=ok (받음 {len(pulled['got'])} · 지움 {len(pulled['removed'])})")
    print(f"PUSH=ok (올림 {len(pushed['put'])} · 지움 {len(pushed['deleted'])})")
    print_conflicts(pulled["conflicts"] + pushed["conflicts"])


def key_file() -> Path:
    return sfbackend.key_file(backend_config_file())


def encryption_line(enc, key_path) -> str:
    if not enc:
        return "off (WARN: 저장소에 닿는 사람은 핸드오프·대화 기록을 그대로 읽을 수 있다)"
    return f"age ({', '.join(enc['recipients'])} · 푸는 키 {tilde(key_path)})"


def logs_lifecycle(logs: str, rules: list) -> str:
    """logs/ 전체에 걸리는 만료 규칙이 있는지. 태그·크기 조건이 붙었거나 logs/ 의 일부에만 걸리면 모자란다."""
    live = [r for r in rules if r["enabled"] and r["expires"]]
    full = [r for r in live if not r["filtered"] and logs.startswith(r["prefix"])]
    if full:
        return f"ok ({', '.join(repr(r['prefix']) for r in full)})"
    part = [r for r in live if logs.startswith(r["prefix"]) or r["prefix"].startswith(logs)]
    if part:
        return (f"partial (WARN: {logs} 의 일부나 조건이 맞는 것에만 만료 규칙이 걸려 있다 — "
                f"{', '.join(repr(r['prefix']) for r in part)})")
    return f"none (WARN: 대화 기록 {logs} 이 계속 쌓인다 — 이 prefix 에 만료(Expiration) 규칙을 거는 게 좋다)"


def bucket_settings(be) -> list:
    """버킷 설정(versioning·lifecycle) 확인. 동기화에 꼭 필요한 건 아니라 읽지 못해도 실패로 치지 않는다 —
    객체 읽기·쓰기만 준 토큰은 버킷 설정을 못 읽고(403), R2 처럼 versioning 조회가 없는 저장소도 있다."""
    out = []
    if hasattr(be, "versioning"):
        try:
            v = be.versioning()
            out.append(f"VERSIONING={v}" + ("" if v == "Enabled" else
                       " (WARN: 지운 파일·덮어쓴 버전을 되살릴 수 없다 — bucket versioning 을 켜는 게 좋다)"))
        except sfbackend.BackendError as e:
            out.append(f"VERSIONING=unknown (확인하지 못했다: {e} — 토큰에 버킷 설정 권한이 없거나 저장소가 지원하지 않는다)")
    if hasattr(be, "lifecycle_rules"):
        logs = be.prefix + "logs/"
        try:
            out.append("LOGS_LIFECYCLE=" + logs_lifecycle(logs, be.lifecycle_rules()))
        except sfbackend.BackendError as e:
            out.append(f"LOGS_LIFECYCLE=unknown (확인하지 못했다: {e} — 저장소 콘솔에서 {logs} 에 만료 규칙이 있는지 본다)")
    return out


def cmd_doctor(a):
    """backend 에 닿는지, conditional write 를 지키는지 확인한다. 실패가 있으면 exit 1."""
    try:
        be = load_backend()
    except sfbackend.BackendError as e:
        print(f"BACKEND=error ({e})")
        sys.exit(1)
    if not be:
        print("BACKEND=none")
        print(f"  {Ctx(None).sync_reason() or 'backend.json 이 없다'}")
        sys.exit(1)
    print(f"BACKEND={be.describe()}")
    if isinstance(be, sfbackend.S3Backend):
        print(f"CREDENTIALS={'env' if sfbackend.env_credentials() else previous_credentials_store()}")
    failed = False
    try:
        print(f"STORE=ok ({be.identity().rsplit('#', 1)[-1]})")
    except sfbackend.BackendError as e:
        print(f"STORE=failed ({e})")
        sys.exit(1)
    try:
        cipher = be.cipher()
        if cipher:
            cipher.check_key()
        print(f"ENCRYPTION={encryption_line(be.encryption, be.key_path)}")
    except sfbackend.BackendError as e:
        print(f"ENCRYPTION=failed ({e})")
        sys.exit(1)

    key = f".doctor/{socket.gethostname().split('.')[0] or 'host'}-{os.getpid()}"
    try:
        e1 = be.put(key, b"1", if_none_match=True)
        try:
            be.put(key, b"2", if_none_match=True)
            print("IF_NONE_MATCH=failed (있는 object 를 덮어썼다 — 새 파일끼리 충돌을 막지 못한다)")
            failed = True
        except sfbackend.PreconditionFailed:
            print("IF_NONE_MATCH=ok")
        e1 = be.stat(key) or e1
        try:
            be.put(key, b"3", if_match="0" * 32)
            print("IF_MATCH=failed (etag 가 달라도 덮어썼다 — 같은 파일을 두 PC 가 고치면 한쪽이 사라진다)")
            failed = True
        except sfbackend.PreconditionFailed:
            print("IF_MATCH=ok")
        e2 = be.put(key, b"4", if_match=be.stat(key))
        if cipher:
            stored, plain = be.get_raw(key)[0], be.get(key)[0]
            if stored.startswith(sfbackend.AGE_MAGIC) and plain == b"4":
                print("SEALED=ok (올라간 내용은 암호문이고 이 PC 의 키로 풀린다)")
            else:
                print("SEALED=failed (올라간 내용이 암호문이 아니거나 다시 풀리지 않는다)")
                failed = True
        if hasattr(be, "delete_request"):
            status = be.delete_request(key, if_match=e1 if e1 != e2 else "0" * 32)
            if status == 412:
                print("DELETE_IF_MATCH=ok")
            else:
                print("DELETE_IF_MATCH=unsupported (저장소가 무시한다 — 동기화의 삭제는 tombstone 을 If-Match PUT 으로 "
                      "하므로 상관없다)")
        else:
            try:
                be.delete(key, if_match="0" * 32)
                print("DELETE_IF_MATCH=failed")
                failed = True
            except sfbackend.PreconditionFailed:
                print("DELETE_IF_MATCH=ok")
        for line in bucket_settings(be):
            print(line)
    except sfbackend.BackendError as e:
        print(f"PROBE=failed ({e})")
        failed = True
    finally:
        try:
            be.delete(key)
        except (sfbackend.BackendError, OSError):
            pass
    sys.exit(1 if failed else 0)


def main(argv=None):
    p = argparse.ArgumentParser(prog="sfstate", description="sessionflow 저장소 기준 상태 경로 + 동기화")
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_dir(sp):
        sp.add_argument("--dir", default=None, help="대상 디렉토리 (기본: 현재 cwd)")
        return sp

    with_dir(sub.add_parser("paths")).set_defaults(fn=cmd_paths)
    with_dir(sub.add_parser("prepare")).set_defaults(fn=cmd_prepare)
    sp = with_dir(sub.add_parser("pull"))
    sp.add_argument("--background", action="store_true")
    sp.set_defaults(fn=cmd_pull)
    sp = with_dir(sub.add_parser("index"))
    sp.add_argument("--prune", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_index)
    sp = with_dir(sub.add_parser("set-priority"))
    sp.add_argument("slug", help="항목 파일 이름 (.md 없이)")
    sp.add_argument("priority", help="|".join(PRIORITIES))
    sp.set_defaults(fn=cmd_set_priority)
    sp = with_dir(sub.add_parser("sync"))
    sp.add_argument("-m", "--message", default="")
    sp.set_defaults(fn=cmd_sync)
    sp = with_dir(sub.add_parser("status"))
    sp.add_argument("--no-pull", action="store_true")
    sp.set_defaults(fn=cmd_status)
    sp = with_dir(sub.add_parser("migrate"))
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_migrate)
    sp = sub.add_parser("migrate-all")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_migrate_all)
    sp = sub.add_parser("init")
    sp.add_argument("--backend", choices=["local", "s3"], required=True)
    sp.add_argument("--path", default="", help="local: 원격으로 쓸 디렉토리")
    sp.add_argument("--bucket", default="", help="s3: bucket")
    sp.add_argument("--endpoint", default="", help="s3: AWS 가 아니면 endpoint URL (R2·MinIO 등)")
    sp.add_argument("--prefix", default="", help="s3: bucket 안에서 쓸 prefix")
    sp.add_argument("--region", default="", help="s3: region (R2 는 auto, 기본 us-east-1)")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--path-style", dest="path_style", action="store_true", default=None)
    g.add_argument("--virtual-host", dest="path_style", action="store_false")
    sp.add_argument("--credentials-stdin", action="store_true",
                    help="s3: 자격증명을 stdin 으로 받아 --credentials-store 가 정한 곳에 저장한다")
    sp.add_argument("--credentials-store", choices=("auto", *sfbackend.CRED_STORES), default="auto",
                    help="s3: 자격증명을 둘 곳 (auto: macOS Keychain → Linux secret-tool → credentials.json)")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--encrypt", dest="encrypt", action="store_true", default=None,
                   help="age 로 암호화한다 (새 저장소의 기본값)")
    g.add_argument("--no-encrypt", dest="encrypt", action="store_false", help="새 저장소를 암호화하지 않는다")
    sp.add_argument("--accept-encryption-change", action="store_true",
                    help="저장소 표시의 암호화 설정이 이 PC 가 쓰던 것과 달라도 받아들인다 (바뀐 이유를 확인한 뒤에만)")
    sp.set_defaults(fn=cmd_init)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    a = p.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
