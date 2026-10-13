#!/usr/bin/env python3
"""sfstate — sessionflow 의 followup / handoff 를 '경로'가 아닌 '저장소' 기준으로 저장하고,
별도 private state repo 로 여러 PC 사이에 동기화한다.

저장 위치 ($HBRNESS_STATE_DIR, 기본 ~/.hbrness/state — private state repo 의 clone):

  <repo-key>/followups/<slug>.md      항목 파일. frontmatter 가 진실원이다.
  <repo-key>/followups/INDEX.md       항목 frontmatter 에서 생성한다 (git 추적 안 함).
  <repo-key>/followups/_config.json   선택: {"resolved_keep": 10}
  <repo-key>/handoffs/<branch>.md     브랜치별 핸드오프.
  _local/<path-key>/...               remote 가 없는 프로젝트 (git 추적 안 함, 동기화 안 함).

<repo-key> 는 프로젝트의 origin remote URL 을 정규화한 값이다 (예: github.com/hbs9312/hbrness).
clone 경로가 PC 마다 달라도 같은 저장소면 같은 키가 나온다.

phase-run / phase-loop / relay 의 오케스트레이션 상태(HANDOFF.md 포함)는 tmux pane 에 묶인
PC 로컬 상태라 여기서 다루지 않는다 — 계속 ~/.hbrness/sessionflow/<path-key>/ 에 있다.

서브커맨드:
  paths       [--dir D]               경로를 KEY=VALUE 로 출력
  prepare     [--dir D]               pull → 레거시 마이그레이션 → INDEX 생성 → paths
  pull        [--dir D] [--background] state repo 를 원격과 맞춘다 (받기만, 실패해도 exit 0).
                                      --dir: 그 프로젝트의 INDEX 도 다시 만든다.
                                      --background: 바로 돌아오고 뒤에서 돈다 (turn 종료 hook 용).
                                      이미 pull 이 돌고 있으면 건너뛴다. 끝나면 PULL_STAMP 를 갱신한다.
  index       [--dir D] [--prune] [--json]
                                      INDEX.md 를 다시 만든다 (--prune: 오래된 resolved 삭제,
                                      --json: 개수와 INDEX 순서의 항목 목록을 JSON 으로 출력)
  sync        [--dir D] [-m MSG]      INDEX 생성·정리 → 이 프로젝트 변경 commit → push
  status      [--dir D] [--no-pull]   이 저장소의 핸드오프·followup 현황
  migrate     [--dir D] [--dry-run]   이 프로젝트의 경로 기준 레거시 데이터를 옮긴다
  migrate-all [--dry-run]             ~/.hbrness/sessionflow/* 전체를 옮긴다
  init        [--remote URL]          state repo 를 clone 하거나 초기화한다

환경변수:
  HBRNESS_HOME          기본 ~/.hbrness
  HBRNESS_STATE_DIR     기본 $HBRNESS_HOME/state
  HBRNESS_STATE_REMOTE  init 에 --remote 가 없을 때 쓰는 remote URL
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

RESOLVED_KEEP_DEFAULT = 10
NET_TIMEOUT = 30
MARKER = ".sfstate-migrated.json"
GITIGNORE = "_local/\n**/followups/INDEX.md\n.DS_Store\n"
STATE_README = """# sessionflow state

sessionflow 의 followup / handoff 를 저장소 기준으로 모아 여러 PC 사이에 동기화하는 repo.
`hbrness` 의 `plugins/sessionflow/scripts/sfstate.py` 가 읽고 쓴다. 직접 고칠 일은 거의 없다.

- `<host>/<owner>/<repo>/followups/<slug>.md` — 후속 조치 항목 (INDEX.md 는 생성물이라 추적 안 함)
- `<host>/<owner>/<repo>/handoffs/<branch>.md` — 브랜치별 핸드오프

새 PC: `python3 <sessionflow>/scripts/sfstate.py init --remote <이 repo URL>`
"""

STATUS_ALIASES = {
    "open": "open", "todo": "open",
    "pending": "pending", "decision": "pending", "decisions pending": "pending", "blocked": "pending",
    "idea": "idea", "ideas": "idea",
    "resolved": "resolved", "done": "resolved", "closed": "resolved",
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


def last_line(text: str) -> str:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return lines[-1] if lines else ""


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
    return state_root() / ".git" / "sfstate-pulled"


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


def state_repo_status() -> str:
    """ok | absent | no-remote"""
    root = state_root()
    if not (root / ".git").exists():
        return "absent"
    code, url, _ = git(["remote", "get-url", "origin"], root)
    return "ok" if code == 0 and url else "no-remote"


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
        return "on" if self.repo_key and state_repo_status() == "ok" else "off"

    def sync_reason(self) -> str:
        if not self.repo_key:
            return "remote 가 없는 프로젝트라 이 PC 에만 저장한다"
        st = state_repo_status()
        if st == "absent":
            return f"state repo 가 없다 — `sfstate.py init --remote <url>` 로 {tilde(state_root())} 를 만든다"
        if st == "no-remote":
            return f"{tilde(state_root())} 에 origin remote 가 없다"
        return ""


def print_paths(ctx: Ctx):
    legacy_single = ctx.followups_dir / "_legacy-FOLLOWUPS.md"
    rows = [
        ("STATE_ROOT", state_root()),
        ("STATE_REPO", state_repo_status()),
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
        try:
            return str(json.loads(v))
        except ValueError:
            return v.strip('"')
    if v.startswith("'") and v.endswith("'") and len(v) >= 2:
        return v[1:-1].replace("''", "'")
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
        # summary 는 title 바로 아래, 나머지는 끝에 둔다
        at = len(lines)
        if key == "summary":
            at = next((i + 1 for i, l in enumerate(lines) if re.match(r"^title\s*:", l)), len(lines))
        lines.insert(at, line)
    return "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]


def first_heading(body: str) -> str:
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else ""


# ─────────────────────────────────────────────────────────────────────────────
# followups INDEX
# ─────────────────────────────────────────────────────────────────────────────

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
    """INDEX 에 보이는 순서로 묶는다: open·pending·idea 는 discovered 최신순, resolved 는 최근 keep 개."""
    by = {k: [i for i in items if i["status"] == k] for k in ("open", "pending", "idea", "resolved")}
    for k in ("open", "pending", "idea"):
        by[k].sort(key=lambda i: (i["discovered"], i["title"]), reverse=True)
    by["resolved"].sort(key=lambda i: (i["resolved"] or i["discovered"], i["title"]), reverse=True)
    return by


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
        f"> Open: {len(by['open'])} · Pending: {len(by['pending'])} · Ideas: {len(by['idea'])} · Resolved: {len(by['resolved'])}",
    ]
    if by["open"]:
        out += ["", "## Open", "", "| 제목 | 한 줄 설명 | Discovered | 상세 |", "|---|---|---|---|"]
        out += [f"| {_cell(i['title'])} | {_cell(i['summary'])} | {i['discovered']} | {link(i)} |" for i in by["open"]]
    if by["pending"]:
        out += ["", "## Decisions Pending", "", "| 주제 | 한 줄 설명 | Discovered | 상세 |", "|---|---|---|---|"]
        out += [f"| {_cell(i['title'])} | {_cell(i['summary'])} | {i['discovered']} | {link(i)} |" for i in by["pending"]]
    if by["idea"]:
        out += ["", "## Ideas / Improvements", ""]
        for i in by["idea"]:
            extra = f" — {_cell(i['summary'])}" if i["summary"] else ""
            out.append(f"- {i['discovered'] or '????-??-??'} {_cell(i['title'])}{extra} ({link(i)})")
    if shown_resolved:
        out += ["", f"## Resolved (최근 {keep})", "", "| 제목 | Resolved | 상세 |", "|---|---|---|"]
        out += [f"| ~~{_cell(i['title'])}~~ | {i['resolved']} | {link(i)} |" for i in shown_resolved]
    fdir.mkdir(parents=True, exist_ok=True)
    ctx.index_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    return {k: len(v) for k, v in by.items()}, pruned


# ─────────────────────────────────────────────────────────────────────────────
# 동기화
# ─────────────────────────────────────────────────────────────────────────────

def _abort_rebase(root: Path):
    if (root / ".git" / "rebase-merge").exists() or (root / ".git" / "rebase-apply").exists():
        git(["rebase", "--abort"], root)


def _pull():
    """반환: (ok|off|failed, 설명)"""
    st = state_repo_status()
    if st != "ok":
        return "off", f"state repo {st}"
    root = state_root()
    c, _, _ = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root)
    if c != 0:
        return "ok", "upstream 없음 (아직 push 한 적 없음)"
    c, _, err = git(["pull", "--rebase", "--autostash", "-q"], root, timeout=NET_TIMEOUT)
    if c != 0:
        _abort_rebase(root)
        return "failed", last_line(err) or f"exit {c}"
    return "ok", ""


def _push(root: Path):
    """반환: (pushed|nochange|committed-local, 설명)"""
    if git(["rev-parse", "-q", "--verify", "HEAD"], root)[0] != 0:
        return "nochange", ""
    c, _, _ = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root)
    if c != 0:
        c, _, err = git(["push", "-q", "-u", "origin", "HEAD"], root, timeout=NET_TIMEOUT)
        return ("pushed", "") if c == 0 else ("committed-local", last_line(err))
    c, ahead, _ = git(["rev-list", "--count", "@{u}..HEAD"], root)
    if c == 0 and ahead == "0":
        return "nochange", ""
    c, _, err = git(["push", "-q"], root, timeout=NET_TIMEOUT)
    if c == 0:
        return "pushed", ""
    c, _, perr = git(["pull", "--rebase", "--autostash", "-q"], root, timeout=NET_TIMEOUT)
    if c != 0:
        _abort_rebase(root)
        return "committed-local", f"원격과 충돌해 rebase 를 되돌렸다 ({last_line(perr)}) — {tilde(root)} 에서 직접 정리"
    c, _, err = git(["push", "-q"], root, timeout=NET_TIMEOUT)
    return ("pushed", "") if c == 0 else ("committed-local", last_line(err))


def _sync(ctx: Ctx, message: str):
    """반환: (pushed|nochange|committed-local|local-only|failed, 설명, pruned)"""
    _, pruned = build_index(ctx, prune=True)
    if ctx.sync != "on":
        return "local-only", ctx.sync_reason(), pruned
    root = state_root()
    rel = str(ctx.project_dir.relative_to(root))
    tracked = git(["ls-files", "--", rel], root)[1]
    if ctx.project_dir.exists() or tracked:
        c, _, err = git(["add", "-A", "--", rel], root)
        if c != 0:
            return "failed", last_line(err), pruned
    c, _, _ = git(["diff", "--cached", "--quiet", "--", rel], root)
    if c == 1:
        msg = f"{ctx.repo_key}: {message or 'update'} ({socket.gethostname()})"
        c, _, err = git(["commit", "-q", "-m", msg, "--", rel], root)
        if c != 0:
            return "failed", last_line(err), pruned
    status, detail = _push(root)
    return status, detail, pruned


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
        st, detail = _pull()
        print(f"PULL={st}" + (f" ({detail})" if detail else ""))
        rep = migrate_ctx(ctx)
        print_migrate_report(rep, "")
        if rep["status"] == "migrated":
            st, detail, _ = _sync(ctx, "migrate path-keyed state")
            print(f"MIGRATE_SYNC={st}" + (f" ({detail})" if detail else ""))
        else:
            build_index(ctx)
    if ctx.sync != "on":
        print(f"SYNC_NOTE={ctx.sync_reason()}")
    print_paths(ctx)


def cmd_pull(a):
    if a.background:
        if state_repo_status() != "ok":
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
            st, detail = _pull()
            if a.dir:
                build_index(Ctx(a.dir))
            if st != "off":
                pull_stamp().touch()
    print(f"PULL={st}" + (f" ({detail})" if detail else ""))


def cmd_index(a):
    ctx = Ctx(a.dir)
    counts, pruned = build_index(ctx, prune=a.prune)
    if a.json:
        keep = resolved_keep(ctx.followups_dir)
        by = group_items(load_items(ctx.followups_dir), keep)
        fields = ("slug", "title", "summary", "status", "discovered", "resolved")
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


def cmd_sync(a):
    ctx = Ctx(a.dir)
    with state_lock():
        st, detail, pruned = _sync(ctx, a.message)
    print(f"SYNC={st}" + (f" ({detail})" if detail else ""))
    if pruned:
        print("PRUNED=" + ",".join(pruned))


def _when(path: Path) -> str:
    """핸드오프 헤더의 Generated 를 먼저 쓴다 — 커밋 시각은 옮기거나 다시 올린 시각일 수 있다."""
    try:
        m = re.search(r"^>\s*Generated:\s*(.+)$", path.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    root = state_root()
    try:
        rel = str(path.relative_to(root))
        c, out, _ = git(["log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M", "--", rel], root)
        if c == 0 and out:
            return out
    except ValueError:
        pass
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M") + " (미동기화)"


def cmd_status(a):
    ctx = Ctx(a.dir)
    if not a.no_pull:
        with state_lock():
            st, detail = _pull()
            build_index(ctx)
        print(f"pull: {st}" + (f" ({detail})" if detail else ""))
    print(f"repo: {ctx.repo_key or tilde(ctx.project_root) + ' (remote 없음)'} · sync {ctx.sync}")
    if ctx.sync != "on":
        print(f"  {ctx.sync_reason()}")
    if ctx.handoff_file.exists():
        print(f"handoff [{ctx.branch}]: {tilde(ctx.handoff_file)} ({_when(ctx.handoff_file)})")
    else:
        print(f"handoff [{ctx.branch or '-'}]: 없음")
    others = []
    if ctx.handoffs_dir.is_dir():
        for f in sorted(ctx.handoffs_dir.rglob("*.md")):
            if f != ctx.handoff_file:
                others.append(f"{f.relative_to(ctx.handoffs_dir).with_suffix('')} ({_when(f)})")
    if others:
        print("다른 브랜치 핸드오프: " + ", ".join(others))
    items = load_items(ctx.followups_dir)
    if items:
        c = {k: sum(1 for i in items if i["status"] == k) for k in ("open", "pending", "idea", "resolved")}
        print(f"followups: open {c['open']} · pending {c['pending']} · idea {c['idea']} · "
              f"resolved {c['resolved']} → {tilde(ctx.index_file)}")
    else:
        print("followups: 없음")


def cmd_migrate(a):
    ctx = Ctx(a.dir)
    with state_lock():
        rep = migrate_ctx(ctx, dry_run=a.dry_run)
        if rep["status"] == "migrated":
            build_index(ctx)
            st, detail, _ = _sync(ctx, "migrate path-keyed state")
            rep["sync"] = st + (f" ({detail})" if detail else "")
    print_migrate_report(rep, "")
    if rep.get("sync"):
        print(f"SYNC={rep['sync']}")


def cmd_migrate_all(a):
    root = legacy_root()
    if not root.is_dir():
        print(f"{tilde(root)} 가 없다 — 옮길 것이 없음")
        return
    with state_lock():
        if not a.dry_run:
            _pull()
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


def _ensure_scaffold(root: Path):
    changed = False
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE, encoding="utf-8")
        changed = True
    rd = root / "README.md"
    if not rd.exists():
        rd.write_text(STATE_README, encoding="utf-8")
        changed = True
    return changed


def cmd_init(a):
    root = state_root()
    remote = a.remote or os.environ.get("HBRNESS_STATE_REMOTE", "")
    with state_lock():
        if (root / ".git").exists():
            c, cur, _ = git(["remote", "get-url", "origin"], root)
            if c != 0 and remote:
                git(["remote", "add", "origin", remote], root)
            elif remote and cur != remote:
                print(f"origin 이 이미 {cur} 로 잡혀 있어 그대로 둔다", file=sys.stderr)
        else:
            if not remote:
                print("init: --remote <state repo URL> 가 필요하다 (또는 HBRNESS_STATE_REMOTE)", file=sys.stderr)
                sys.exit(1)
            aside = None
            if root.exists() and any(root.iterdir()):
                aside = root.with_name(f"{root.name}.pre-init-{dt.datetime.now():%Y%m%d%H%M%S}")
                root.rename(aside)
            root.parent.mkdir(parents=True, exist_ok=True)
            c, _, err = git(["clone", "-q", remote, str(root)], root.parent, timeout=180)
            if c != 0:
                if aside:
                    aside.rename(root)
                print(f"init: clone 실패 — {last_line(err)}", file=sys.stderr)
                sys.exit(1)
            if aside:
                for f in aside.rglob("*"):
                    dst = root / f.relative_to(aside)
                    if f.is_file() and not dst.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, dst)
                print(f"기존 {tilde(root)} 내용을 {tilde(aside)} 로 옮기고, 없던 파일만 다시 복사했다")
        if _ensure_scaffold(root):
            git(["add", ".gitignore", "README.md"], root)
            git(["commit", "-q", "-m", "init sessionflow state repo"], root)
        git(["add", "-A"], root)
        if git(["diff", "--cached", "--quiet"], root)[0] == 1:
            git(["commit", "-q", "-m", f"import local state ({socket.gethostname()})"], root)
        if git(["rev-parse", "-q", "--verify", "HEAD"], root)[0] == 0:
            st, detail = _push(root)
        else:
            st, detail = "nochange", ""
    print(f"STATE_ROOT={root}")
    print(f"STATE_REPO={state_repo_status()}")
    print(f"PUSH={st}" + (f" ({detail})" if detail else ""))


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
    sp.add_argument("--remote", default="")
    sp.set_defaults(fn=cmd_init)

    a = p.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
