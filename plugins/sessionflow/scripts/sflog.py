#!/usr/bin/env python3
"""sflog — 코딩 에이전트(Claude Code / Codex / Grok / Devin)의 대화 transcript 를 backend 에 모은다.

각 도구가 이미 남기는 transcript 원본을 그대로 올린다 (공통 형식 변환은 읽을 때 한다 — 도구가 형식을
바꿔도 올린 내용이 깨지지 않게). 올리기 전에 비밀값을 가린다. 훅(sfhook.py)이 turn 이 끝날 때마다,
그리고 세션이 끝날 때 부른다.

원격 key (backend 의 logs/ 아래, followup/handoff 의 repos/ 와 따로):
  logs/<repo-key|_norepo>/<tool>/<session-id>/meta.json          세션 정보 (도구·저장소·브랜치·시각…)
  logs/<repo-key|_norepo>/<tool>/<session-id>/000001.jsonl.gz    JSONL transcript 를 늘어난 만큼씩 (Claude·Codex·Grok)
  logs/<repo-key|_norepo>/<tool>/<session-id>/transcript.json.gz JSON 한 덩어리 transcript 의 최신본 (Devin)

S3 object 는 뒤에 이어 쓸 수 없어서, JSONL 은 지난번에 올린 곳(offset) 뒤로 늘어난 줄만 segment 로 올린다.
offset 은 ~/.hbrness/logs/sessions/<tool>-<session>.json 에 적는다.

  logs/<repo-key|_norepo>/manual/<id>/transcript.md              훅이 없는 곳에서 save 로 남긴 기록

서브커맨드:
  collect --tool T --session S [--transcript P] [--cwd D] [--final]
          한 세션의 새 내용을 올린다. backend 가 없으면 아무것도 하지 않는다.
          --final: 세션 끝 — 마지막 줄이 줄바꿈 없이 끝나도 올린다.
  list    [--dir D] [--all-repos] [--tool T] [--limit N] [--json]
          이 저장소(또는 전체)의 세션을 최근 것부터. meta.json 만 읽는다.
  show    SESSION [--dir D] [--all-repos] [--no-tools] [--full] [--raw] [--out FILE]
          세션 하나를 도구와 상관없이 같은 형식(### user / ### assistant / → 도구 / ← 결과)으로 보여준다.
          SESSION 은 session id 의 앞부분이면 된다.
  search  QUERY [--dir D] [--all-repos] [--days N] [--tool T] [--regex] [--limit N]
          최근 N일(기본 30) 세션에서 글을 찾는다.
  save    --title T [--dir D] [--file F]      (없으면 stdin)
          훅이 없는 곳(웹 채팅 등)의 대화·요약을 manual 기록으로 남긴다. 비밀값을 가린 뒤 올린다.

읽은 object 는 ~/.hbrness/logs/cache/ 에 etag 와 함께 둔다 — 바뀐 것만 다시 받는다 (암호화한 저장소면 푼 내용).

비밀값 가리기 (올리기 전에, 저장소 암호화와 따로):
  - 아래 SECRET_PATTERNS (알려진 토큰 접두어) + ~/.hbrness/redact.txt (한 줄에 정규식 하나, # 주석)
  - URL 안의 비밀번호 (postgres://user:비밀번호@host)
  - .env 꼴 줄(NAME=value)은 이름과 상관없이 값이 무작위 문자열처럼 보이면
  - password=… · "api_key": "…" 처럼 이름이 비밀값인 것의 값
  - gitleaks 가 설치돼 있으면 가린 결과를 한 번 더 훑어 찾은 것도 가린다
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import sys
import traceback
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sfbackend  # noqa: E402
import sfstate  # noqa: E402

TOOLS = ("claude", "codex", "grok", "devin")
SEGMENT_MAX = 8 * 1024 * 1024  # 한 segment 에 넣는 원문 상한. 처음 붙는 긴 세션도 나눠 올린다.
HEAD_LEN = 4096  # 파일이 다시 쓰였는지 볼 때 비교하는 앞부분 길이
LOG_KEEP = 256 * 1024  # collect.log 상한

# 패턴 앞 경계: 보통의 단어 경계, 또는 JSON escape(\n·\t …) 바로 뒤 — 문자열 안에 JSON 이 한 번 더 들어 있을 때.
B = r"(?:(?<=\\[nrtbf])|\b)"
SECRET_PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S)),
    ("age-secret-key", re.compile(B + r"AGE-SECRET-KEY-(?:PQ-)?1[0-9A-Z]{50,}")),
    ("aws-access-key", re.compile(B + r"(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(B + r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("gitlab-token", re.compile(B + r"gl(?:pat|dt|ptt|rt|soat|cbt|imt|ffct)-[A-Za-z0-9_\-]{20,}")),
    ("anthropic-key", re.compile(B + r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-key", re.compile(B + r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("stripe-key", re.compile(B + r"(?:(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}|whsec_[A-Za-z0-9+/=]{24,})")),
    ("slack-token", re.compile(B + r"(?:xox[abprse]-[A-Za-z0-9\-]{10,}|xapp-\d-[A-Za-z0-9\-]{10,})")),
    ("npm-token", re.compile(B + r"npm_[A-Za-z0-9]{36,}")),
    ("pypi-token", re.compile(B + r"pypi-[A-Za-z0-9_\-]{40,}")),
    ("huggingface-token", re.compile(B + r"hf_[A-Za-z0-9]{30,}")),
    ("shopify-token", re.compile(B + r"shp(?:at|ss|ca|pa)_[a-fA-F0-9]{32}")),
    ("digitalocean-token", re.compile(B + r"do[opr]_v1_[a-f0-9]{64}")),
    ("sendgrid-key", re.compile(B + r"SG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}")),
    ("google-api-key", re.compile(B + r"AIza[0-9A-Za-z_\-]{35}")),
    ("google-oauth", re.compile(B + r"(?:ya29\.[A-Za-z0-9_\-]{20,}|GOCSPX-[A-Za-z0-9_\-]{20,})")),
    ("groq-key", re.compile(B + r"gsk_[A-Za-z0-9]{40,}")),
    ("xai-key", re.compile(B + r"xai-[A-Za-z0-9]{40,}")),
    ("databricks-token", re.compile(B + r"dapi[a-f0-9]{32}\b")),
    ("linear-key", re.compile(B + r"lin_(?:api|oauth)_[A-Za-z0-9]{32,}")),
    ("notion-token", re.compile(B + r"(?:ntn_[A-Za-z0-9]{40,}|secret_[A-Za-z0-9]{43}\b)")),
    ("sentry-token", re.compile(B + r"sntry[su]_[A-Za-z0-9_=+/\-]{20,}")),
    ("atlassian-token", re.compile(B + r"ATATT[A-Za-z0-9_\-=]{20,}")),
    ("jwt", re.compile(B + r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("bearer", re.compile(r"(?i)" + B + r"bearer\s+[A-Za-z0-9._~+/=\-]{16,}")),
]
# scheme://user:비밀번호@host 의 비밀번호. user 와 host 는 남긴다.
URL_PASSWORD = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]{1,20}://[^\s:/@\"'<>\\]{0,128}):([^\s/@\"'<>\\]{1,256})@")
# .env 꼴 줄: NAME=value 가 한 줄을 다 차지한다. 줄 앞의 `export ` 와 Read 도구의 줄 번호(`  12→`, `12\t`)도 받는다.
ENV_LINE = re.compile(
    r"(?m)(?:^|(?<=\\n))((?:[ \t]*\d+(?:→|\t|\\t))?[ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]{0,63}[ \t]*=[ \t]*)"
    r"([\"']?)([A-Za-z0-9+/=_.~\-]{12,512})\2(?=[ \t]*(?:\r?$|\\[nr]))")
_SENSITIVE = (r"password|passwd|passphrase|secret|secret[_-]?access[_-]?key|api[_-]?key|access[_-]?token"
              r"|auth[_-]?token|client[_-]?secret|token|private|dsn|signing[_-]?key|encryption[_-]?key|master[_-]?key")
_NAME = r"(?:" + _SENSITIVE + r")(?:[_-]?key)?"  # SECRET_KEY · PRIVATE_KEY 처럼 뒤에 _KEY 가 붙은 이름도
# 글 속의 `password=…`, `DB_PASSWORD="two words"`, `"api_key": "…"` 꼴은 값만 가린다. 따옴표로 묶인 값은
# 닫는 따옴표까지 통째로(짧아도, 공백이 있어도), 안 묶인 값은 공백·구분자 전까지.
ASSIGNMENT = re.compile(
    r"(?i)" + B + r"((?:[A-Za-z0-9]{1,32}[_-]){0,4}" + _NAME + r")"  # 접두어 반복에 상한 — 긴 base64 에서 느려지지 않게
    r"(\\?[\"']?\s*[:=]\s*)"
    r"(\\\"(?:(?!\\\").)*\\\"|\"[^\"\n]*\"|'[^'\n]*'|[^\s\"'\\,;}&)]+)")
# JSON 객체에서 이름이 이런 key 의 값(문자열·숫자)은 통째로 가린다. 예: {"db_password": 123456789}
SENSITIVE_KEY = re.compile(r"(?i)^(?:.*[_-])?" + _NAME + r"$")
NOT_SECRET = {"true", "false", "null", "none", "undefined"}  # "private": true 같은 설정값
MASK = "[REDACTED:assignment]"


def logs_home() -> Path:
    return sfstate.hbrness_home() / "logs"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def safe_part(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", s or "").strip(".-") or "unknown"


def note(msg: str):
    """뒤에서 조용히 도는 수집기의 실패를 남긴다 (훅은 아무것도 출력하지 않으므로)."""
    try:
        f = logs_home() / "collect.log"
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists() and f.stat().st_size > LOG_KEEP:
            f.write_text(f.read_text(encoding="utf-8", errors="replace")[-LOG_KEEP // 2:], encoding="utf-8")
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"{now_iso()} {msg}\n")
    except OSError:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 비밀값 가리기
# ─────────────────────────────────────────────────────────────────────────────

def user_patterns():
    out = []
    f = sfstate.hbrness_home() / "redact.txt"
    try:
        lines = f.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(("custom", re.compile(line)))
        except re.error as e:
            note(f"redact.txt 의 정규식을 건너뜀: {line!r} ({e})")
    return out


def _mask_assignment(m) -> str:
    value = m.group(3)
    for q in ('\\"', '"', "'"):
        if value.startswith(q) and value.endswith(q) and len(value) >= 2 * len(q):
            if value[len(q):].startswith("[REDACTED:"):
                return m.group(0)
            return f"{m.group(1)}{m.group(2)}{q}{MASK}{q}"
    if value.startswith("[REDACTED:") or value.lower() in NOT_SECRET:
        return m.group(0)
    return f"{m.group(1)}{m.group(2)}{MASK}"


def looks_random(value: str) -> bool:
    """비밀값처럼 무작위로 보이나: 글자와 숫자가 섞였고, 글자당 엔트로피가 3 bit 이상. 경로는 빼 둔다."""
    if value.startswith(("/", "~/", "./", "../")) or not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        return False
    n = len(value)
    return -sum(c / n * math.log2(c / n) for c in collections.Counter(value).values()) >= 3.0


def _mask_env(m) -> str:
    if not looks_random(m.group(3)):
        return m.group(0)
    return f"{m.group(1)}{m.group(2)}[REDACTED:env]{m.group(2)}"


def redact_text(text: str, extra=()) -> str:
    for name, pat in [*SECRET_PATTERNS, *extra]:
        text = pat.sub(f"[REDACTED:{name}]", text)
    text = URL_PASSWORD.sub(r"\1:[REDACTED:url-password]@", text)
    text = ENV_LINE.sub(_mask_env, text)
    return ASSIGNMENT.sub(_mask_assignment, text)


def redact_value(v, extra=(), key=None):
    """JSON 값을 걸어 다니며 가린다. 반환: (새 값, 바뀌었나). 문자열은 풀린 글자 그대로 검사하므로
    \n 같은 escape 경계에 막히지 않고, 결과를 다시 직렬화하니 JSON 이 깨지지 않는다."""
    if key is not None and SENSITIVE_KEY.match(key) and (
            (isinstance(v, str) and v) or (isinstance(v, (int, float)) and not isinstance(v, bool))):
        return MASK, v != MASK
    if isinstance(v, str):
        new = redact_text(v, extra)
        return new, new != v
    if isinstance(v, dict):
        changed, out = False, {}
        for k, x in v.items():
            out[k], c = redact_value(x, extra, k)
            changed |= c
        return out, changed
    if isinstance(v, list):
        changed, out = False, []
        for x in v:
            y, c = redact_value(x, extra)
            out.append(y)
            changed |= c
        return out, changed
    return v, False


def redact_json_bytes(data: bytes, extra=()) -> bytes:
    """JSON 한 덩어리를 가린다. 바뀐 게 없으면 원래 바이트를 그대로 둔다. JSON 이 아니면 글로 보고 가린다."""
    if not data.strip():
        return data
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return redact_text(data.decode("utf-8", "surrogateescape"), extra).encode("utf-8", "surrogateescape")
    new, changed = redact_value(obj, extra)
    if not changed:
        return data
    try:
        return json.dumps(new, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except UnicodeEncodeError:  # 짝 없는 surrogate(\ud800 등) — escape 해 둔다
        return json.dumps(new, separators=(",", ":")).encode("ascii")


def redact_jsonl(data: bytes, extra=()) -> bytes:
    """JSONL 을 줄마다 가린다. 줄바꿈은 그대로 둔다."""
    out = []
    for line in data.splitlines(keepends=True):
        body = line.rstrip(b"\r\n")
        out.append(redact_json_bytes(body, extra) + line[len(body):])
    return b"".join(out)


def redact(text: str, extra=()) -> str:
    """글 하나를 가린다. JSON 이면 JSON 으로 다룬다."""
    return redact_json_bytes(text.encode("utf-8", "surrogateescape"), extra).decode("utf-8", "surrogateescape")


def gitleaks_patterns(data: bytes) -> list:
    """gitleaks 가 있으면 가린 결과를 한 번 더 훑는다. 반환: 찾은 비밀값을 그대로 가리는 패턴 (없거나 실패하면 []).
    저장소의 .gitleaks.toml·.gitleaksignore 가 걸러 내지 않게 빈 디렉토리에서 돌린다."""
    exe = sfbackend.which("gitleaks")
    if not exe or not data.strip():
        return []
    cwd = logs_home() / "gitleaks"
    try:
        cwd.mkdir(parents=True, exist_ok=True)
        p = subprocess.run([exe, "stdin", "--no-banner", "--no-color", "--log-level", "error", "--exit-code", "0",
                            "--redact=0", "--report-format", "json", "--report-path", "-"],
                           input=data, capture_output=True, cwd=cwd, timeout=60)
        findings = json.loads(p.stdout or b"[]") if p.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        note(f"gitleaks 를 건너뜀: {e}")
        return []
    if not isinstance(findings, list):
        note(f"gitleaks 를 건너뜀: exit {p.returncode} {p.stderr[-300:]!r}")
        return []
    secrets = set()
    for f in findings:
        secret = f.get("Secret") if isinstance(f, dict) else None
        if not isinstance(secret, str) or len(secret) < 8 or secret.startswith("[REDACTED:"):
            continue
        secrets.add(secret)
        with contextlib.suppress(ValueError):  # JSONL 에서 찾은 것 — 풀린 글자로도 가린다
            secrets.add(json.loads(f'"{secret}"'))
    return [("gitleaks", re.compile(re.escape(s))) for s in sorted(secrets, key=len, reverse=True)]


def scrub(data: bytes, extra, redactor) -> bytes:
    """redactor(data, extra) 로 가린 뒤 gitleaks 가 더 찾으면 그것까지 넣어 처음부터 다시 가린다."""
    out = redactor(data, extra)
    found = gitleaks_patterns(out)
    return redactor(data, [*extra, *found]) if found else out


def utf8(text: str) -> str:
    """짝 없는 surrogate 를 ? 로 — meta.json 에 들어갈 글이 UTF-8 로 바뀌게."""
    return text.encode("utf-8", "replace").decode("utf-8")


def scrub_text(text: str, extra) -> str:
    """글(제목·save 본문)을 scrub 처럼 가린다. 짝 없는 surrogate 가 섞여 있어도 깨지지 않는다."""
    out = redact_text(text, extra)
    found = gitleaks_patterns(out.encode("utf-8", "surrogatepass"))
    return redact_text(text, [*extra, *found]) if found else out


# ─────────────────────────────────────────────────────────────────────────────
# transcript 위치
# ─────────────────────────────────────────────────────────────────────────────

def grok_transcript(session: str, cwd: str):
    """Grok 은 훅에 transcript 경로를 주지 않는다. ~/.grok/sessions/<URL 인코딩한 cwd>/<session>/chat_history.jsonl"""
    base = Path(os.environ.get("GROK_HOME") or Path.home() / ".grok") / "sessions"
    if cwd:
        p = base / urllib.parse.quote(cwd, safe="") / session / "chat_history.jsonl"
        if p.is_file():
            return p
    hits = sorted(base.glob(f"*/{glob_escape(session)}/chat_history.jsonl"))
    return hits[0] if hits else None


def glob_escape(s: str) -> str:
    return re.sub(r"([*?\[\]])", r"[\1]", s)


def find_transcript(tool: str, session: str, transcript: str, cwd: str):
    if transcript:
        p = Path(transcript).expanduser()
        return p if p.is_file() else None
    if tool == "grok":
        return grok_transcript(session, cwd)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 세션 상태
# ─────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def session_state(tool: str, session: str):
    """세션마다 상태 파일 하나. 같은 세션의 수집기가 겹쳐 돌지 않게 flock 을 잡는다."""
    d = logs_home() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    name = f"{tool}-{safe_part(session)}"
    with open(d / f"{name}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        f = d / f"{name}.json"
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        try:
            yield st
        finally:
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            os.replace(tmp, f)
            fcntl.flock(lock, fcntl.LOCK_UN)


def remote_dir(st: dict, tool: str, session: str, cwd: str) -> str:
    """처음 수집할 때 정한 자리를 세션 내내 쓴다 — 도중에 cd 해도 한 세션은 한 곳에 모인다."""
    if not st.get("prefix"):
        ctx = sfstate.Ctx(cwd) if cwd and os.path.isdir(cwd) else None
        st["repo_key"] = ctx.repo_key if ctx else None
        st["branch"] = ctx.branch if ctx else None
        st["cwd"] = cwd
        st["prefix"] = f"logs/{st['repo_key'] or '_norepo'}/{tool}/{safe_part(session)}"
        st["started"] = now_iso()
    return st["prefix"]


# ─────────────────────────────────────────────────────────────────────────────
# 올리기
# ─────────────────────────────────────────────────────────────────────────────

def upload_jsonl(be, st: dict, src: Path, prefix: str, final: bool, extra) -> int:
    """지난 offset 뒤로 늘어난 완성된 줄을 segment 로 올린다. 반환: 올린 segment 수."""
    size = src.stat().st_size
    offset = int(st.get("offset", 0))
    with open(src, "rb") as fh:
        # 파일이 다시 쓰였으면(압축·재시작 등) 처음부터 새 segment 로 잇는다. 줄었거나 앞부분이 달라졌으면 그렇다.
        head_len = int(st.get("head_len", 0))
        if size < offset or (head_len and hashlib.sha256(fh.read(head_len)).hexdigest() != st.get("head_sha256")):
            st["rewrites"] = int(st.get("rewrites", 0)) + 1
            offset, head_len = 0, 0
        sent = upload_lines(be, st, fh, size, offset, prefix, final, extra)
        if st["offset"] and head_len < HEAD_LEN:
            fh.seek(0)
            head = fh.read(min(HEAD_LEN, st["offset"]))
            st["head_len"], st["head_sha256"] = len(head), hashlib.sha256(head).hexdigest()
    return sent


def next_chunk(fh, offset: int, size: int, final: bool) -> bytes:
    """offset 부터 줄 경계에서 끝나는 덩어리. 비밀값이 segment 경계에 걸려 반씩 나뉘지 않게, 줄을 자르지 않는다.
    한 줄이 SEGMENT_MAX 보다 길면 그 줄 끝까지 읽는다. 줄이 아직 덜 쓰였으면 b"" (final 이면 끝까지)."""
    fh.seek(offset)
    chunk = fh.read(min(SEGMENT_MAX, size - offset))
    cut = chunk.rfind(b"\n")
    if cut >= 0:
        return chunk[:cut + 1]
    parts, pos = [chunk], offset + len(chunk)
    while pos < size:
        block = fh.read(min(1 << 20, size - pos))
        if not block:
            break
        i = block.find(b"\n")
        if i >= 0:
            parts.append(block[:i + 1])
            return b"".join(parts)
        parts.append(block)
        pos += len(block)
    return b"".join(parts) if final else b""


def upload_lines(be, st, fh, size, offset, prefix, final, extra) -> int:
    sent = 0
    while offset < size:
        chunk = next_chunk(fh, offset, size, final)
        if not chunk:
            break  # 아직 쓰는 중인 줄 — 다음에 올린다
        seq = int(st.get("seq", 0)) + 1
        st["meta_dirty"] = True  # 올린 뒤 meta.json 이 실패해도 다음 수집이 다시 쓴다
        be.put(f"{prefix}/{seq:06d}.jsonl.gz", gzip.compress(scrub(chunk, extra, redact_jsonl), mtime=0))
        offset += len(chunk)
        st["seq"], st["offset"] = seq, offset
        sent += 1
    st["offset"] = offset
    return sent


def upload_snapshot(be, st: dict, src: Path, prefix: str, extra) -> int:
    data = src.read_bytes()
    h = hashlib.sha256(data).hexdigest()
    if st.get("snapshot_sha256") == h:
        return 0
    st["meta_dirty"] = True
    be.put(f"{prefix}/transcript.json.gz", gzip.compress(scrub(data, extra, redact_json_bytes), mtime=0))
    st["snapshot_sha256"] = h
    return 1


def reset_progress(st: dict):
    """원격에 올린 진행(offset·segment 번호·snapshot)을 지운다 — 다른 저장소에 처음부터 올리게."""
    for k in ("offset", "seq", "head_len", "head_sha256", "snapshot_sha256", "meta_sent", "rewrites"):
        st.pop(k, None)
    st["meta_dirty"] = True


def write_meta(be, st: dict, tool: str, session: str):
    st["updated"] = now_iso()
    meta = {
        "tool": tool, "session_id": session, "repo_key": st.get("repo_key"),
        "branch": st.get("branch"), "cwd": st.get("cwd"),
        "host": socket.gethostname().split(".")[0], "format": st.get("format"),
        "segments": int(st.get("seq", 0)), "rewrites": int(st.get("rewrites", 0)),
        "started": st.get("started"), "updated": st["updated"], "ended": st.get("ended"),
        "title": st.get("title") or "",
    }
    be.put(f"{st['prefix']}/meta.json", json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))
    st["meta_sent"], st["meta_dirty"] = True, False


def collect(tool: str, session: str, transcript: str = "", cwd: str = "", final: bool = False) -> str:
    """반환: 한 일을 한 줄로 (off | no-transcript | uploaded N | nochange)."""
    be = sfstate.load_backend()
    if not be:
        return "off"
    src = find_transcript(tool, session, transcript, cwd)
    with session_state(tool, session) as st:
        store = be.identity()  # 표시가 없는 저장소에는 올리지 않는다
        if st.get("store") != store:
            # 진행 기록은 저장소에 묶인다. backend 를 바꿨거나 저장소를 새로 만들었으면 처음부터 올린다.
            if st.get("store"):
                reset_progress(st)
            st["store"] = store
        if final:
            st["ended"] = now_iso()
            st["meta_dirty"] = True
        if src is None:
            # transcript 가 사라졌어도 이미 올린 세션이면 끝났다는 것만은 올린다
            if st.get("prefix") and (st.get("meta_dirty") or not st.get("meta_sent")):
                write_meta(be, st, tool, session)
            return "no-transcript"
        prefix = remote_dir(st, tool, session, cwd)
        st["source"] = str(src)
        extra = user_patterns()
        if src.suffix == ".jsonl":
            st["format"] = "jsonl-segments"
            sent = upload_jsonl(be, st, src, prefix, final, extra)
        else:
            st["format"] = "json-snapshot"
            sent = upload_snapshot(be, st, src, prefix, extra)
        if not st.get("title"):
            title = derive_title(tool, src, extra)
            if title:
                st["title"], st["meta_dirty"] = title, True
        if st.get("meta_dirty") or not st.get("meta_sent"):
            write_meta(be, st, tool, session)
        return f"uploaded {sent}" if sent else "nochange"


def cmd_collect(a):
    try:
        print(f"COLLECT={collect(a.tool, a.session, a.transcript, a.cwd, a.final)}")
    except (sfbackend.BackendError, OSError) as e:
        note(f"collect {a.tool} {a.session}: {e}")
        print(f"COLLECT=failed ({e})")
        sys.exit(1)
    except Exception:  # 뒤에서 도는 수집기라 남기지 않으면 아무도 모른다
        note(f"collect {a.tool} {a.session}: {traceback.format_exc()}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# 읽기 — 도구마다 다른 transcript 를 같은 사건 목록으로
# ─────────────────────────────────────────────────────────────────────────────
# 사건(event): {"role": user|assistant|tool|result|note, "text": str, "ts": str|None, "name": 도구 이름|None}

# 도구가 사용자 말인 것처럼 끼워 넣는 환경·지침 블록 — 사람이 쓴 말이 아니다
INJECTED_TAGS = ("environment_context", "user_instructions", "permissions", "turn_aborted", "user_info",
                 "system-reminder", "local-command-caveat")
INJECTED_BLOCK = re.compile(r"<(" + "|".join(map(re.escape, INJECTED_TAGS)) + r")\b[^>]*>.*?</\1>\s*", re.S)
INJECTED_OPEN = tuple(f"<{t}" for t in INJECTED_TAGS) + ("# AGENTS.md",)


def human(text: str) -> str:
    """끼워 넣은 블록을 떼어 낸 사람의 말. 같은 글 안에 사람이 쓴 말이 남아 있으면 그것만 남긴다."""
    rest = INJECTED_BLOCK.sub("", text)
    if rest.lstrip().startswith(INJECTED_OPEN):  # 닫히지 않은 블록·AGENTS.md 지침 — 통째로 끼워 넣은 것
        return ""
    return rest.strip()


def human_of(content) -> str:
    """사용자 메시지의 블록마다 끼워 넣은 것을 따로 걸러 낸 뒤 이어 붙인다 — 한 블록 때문에 전체를 버리지 않게."""
    blocks = content if isinstance(content, list) else [content]
    return "\n".join(t for t in (human(text_of([b]) if not isinstance(b, str) else b) for b in blocks) if t)


def ev(role, text, ts=None, name=None) -> dict:
    return {"role": role, "text": text if isinstance(text, str) else "", "ts": ts, "name": name}


def text_of(content) -> str:
    """문자열이거나 [{type: text|input_text|output_text, text}] 블록 목록일 때 글만 모은다."""
    if isinstance(content, str):
        return content
    out = []
    for b in content if isinstance(content, list) else []:
        if isinstance(b, str):
            out.append(b)
        elif isinstance(b, dict) and isinstance(b.get("text"), str):
            out.append(b["text"])
    return "\n".join(out)


def dump(v) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def events_claude(records):
    for d in records:
        t, ts = d.get("type"), d.get("timestamp")
        if t not in ("user", "assistant") or d.get("isMeta"):
            continue
        content = (d.get("message") or {}).get("content")
        if isinstance(content, str):
            text = human(content) if t == "user" else content
            if text:
                yield ev(t, text, ts)
            continue
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                text = human(b.get("text") or "") if t == "user" else b.get("text")
                if text:
                    yield ev(t, text, ts)
            elif b.get("type") == "tool_use":
                yield ev("tool", dump(b.get("input")), ts, b.get("name"))
            elif b.get("type") == "tool_result":
                yield ev("result", text_of(b.get("content")), ts)


def events_codex(records):
    for d in records:
        if d.get("type") != "response_item":
            continue
        p, ts = d.get("payload") or {}, d.get("timestamp")
        kind = p.get("type")
        if kind == "message" and p.get("role") in ("user", "assistant"):
            text = human_of(p.get("content")) if p["role"] == "user" else text_of(p.get("content"))
            if text:
                yield ev(p["role"], text, ts)
        elif kind in ("function_call", "custom_tool_call", "local_shell_call"):
            yield ev("tool", dump(p.get("arguments") or p.get("input") or p.get("action")), ts, p.get("name"))
        elif kind in ("function_call_output", "custom_tool_call_output"):
            out = p.get("output")
            yield ev("result", text_of(out) if isinstance(out, list) else dump(out), ts)


def events_grok(records):
    for d in records:
        t, ts = d.get("type"), d.get("timestamp")
        if t == "user" and not d.get("synthetic_reason"):
            text = human_of(d.get("content"))
            if text:
                yield ev("user", text, ts)
        elif t == "assistant":
            if d.get("content"):
                yield ev("assistant", text_of(d.get("content")), ts)
            for c in d.get("tool_calls") or []:
                if isinstance(c, dict):
                    yield ev("tool", dump(c.get("arguments")), ts, c.get("name"))
        elif t == "tool_result":
            yield ev("result", text_of(d.get("content")), ts)


def events_devin(doc):
    for st in (doc.get("steps") or []) if isinstance(doc, dict) else []:
        if not isinstance(st, dict):
            continue
        src, ts = st.get("source"), st.get("timestamp")
        if src == "user" and human(dump(st.get("message"))):
            yield ev("user", human(dump(st.get("message"))), ts)
        elif src == "agent":
            if st.get("message"):
                yield ev("assistant", dump(st.get("message")), ts)
            for c in st.get("tool_calls") or []:
                if isinstance(c, dict):
                    yield ev("tool", dump(c.get("arguments")), ts, c.get("function_name"))
            for r in (st.get("observation") or {}).get("results") or []:
                if isinstance(r, dict):
                    yield ev("result", dump(r.get("content")), ts)


JSONL_EVENTS = {"claude": events_claude, "codex": events_codex, "grok": events_grok}


def jsonl_records(data: bytes):
    for line in data.splitlines():
        try:
            d = json.loads(line)
        except (ValueError, UnicodeDecodeError, RecursionError):
            continue
        if isinstance(d, dict):
            yield d


def events_from(tool: str, fmt: str, data: bytes) -> list:
    if fmt == "markdown":
        return [ev("note", data.decode("utf-8", "replace"))]
    if fmt == "json-snapshot":
        try:
            return list(events_devin(json.loads(data)))
        except (ValueError, UnicodeDecodeError, RecursionError):
            return []
    return list(JSONL_EVENTS.get(tool, events_claude)(jsonl_records(data)))


def derive_title(tool: str, src: Path, extra=()) -> str:
    """첫 사용자 말 한 줄. meta.json 으로 올라가므로 비밀값을 가린다."""
    try:
        with open(src, "rb") as fh:
            data = fh.read(2 * 1024 * 1024)
        fmt = "jsonl-segments" if src.suffix == ".jsonl" else "json-snapshot"
        # 올리는 기록과 똑같이 먼저 가린 뒤에 고른다 — 제목에는 올라간 기록에 있는 글만 들어간다
        if fmt == "jsonl-segments":
            data = redact_jsonl(data[:data.rfind(b"\n") + 1], extra)
        else:
            data = redact_json_bytes(data, extra)
        for e in events_from(tool, fmt, data):
            if e["role"] != "user":
                continue
            # 원문 그대로 먼저 가린다 — 줄을 합친 뒤에는 줄 단위 사용자 패턴이 안 걸린다
            text = redact_text(e["text"], extra)
            cmd = re.search(r"<command-name>(.*?)</command-name>", text, re.S)
            if cmd:  # Claude 슬래시 명령 — 인자가 있을 때만 제목감이다 (/clear 같은 건 건너뛴다)
                args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
                plain = f"{cmd.group(1).strip()} {args.group(1).strip()}" if args and args.group(1).strip() else ""
            else:
                plain = " ".join(re.sub(r"<[^>]+>", " ", text).split())
                if re.fullmatch(r"/\S+", plain):
                    plain = ""
            if plain:
                return utf8(scrub_text(" ".join(plain.split()), extra)[:100])
    except OSError:
        pass
    return ""


def instant(ts) -> dt.datetime:
    """ISO 시각 → 비교할 수 있는 시점. PC 마다 offset 이 달라도 같은 순간이면 같다. 못 읽으면 아주 옛날."""
    try:
        t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return t if t.tzinfo else t.astimezone()


def clip(text: str, limit) -> str:
    text = text.strip()
    if limit is None or len(text) <= limit:
        return text
    return text[:limit] + f" … (+{len(text) - limit}자)"


def render(events, tools=True, full=False) -> str:
    out = []
    for e in events:
        text = e["text"].strip()
        if e["role"] in ("tool", "result"):
            if not tools:
                continue
            if e["role"] == "tool":
                out.append(f"→ {e['name'] or 'tool'}: {clip(text, None if full else 300)}")
            elif text:
                out += [f"← {clip(text, None if full else 500)}", ""]
            continue
        if not text:
            continue
        out += [f"### {e['role']}" + (f" · {e['ts']}" if e["ts"] else ""), "", text, ""]
    return "\n".join(out).rstrip() + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# 원격 기록 찾기 (캐시)
# ─────────────────────────────────────────────────────────────────────────────

class Remote:
    """backend 의 logs/ 를 읽는다. 받은 object 는 etag 와 함께 캐시해 두고 바뀐 것만 다시 받는다."""

    def __init__(self, be):
        self.be = be
        store = be.identity()
        self.dir = logs_home() / "cache" / hashlib.sha256(store.encode()).hexdigest()[:16]

    def fetch(self, key: str, etag: str) -> bytes:
        """캐시 파일 이름에 etag 를 넣는다(<key>@<etag>). 그래서 index 가 따로 없고, 여러 명령이 겹쳐 돌아도
        파일마다 통째로 바꿔 넣으니(os.replace) 반쯤 쓴 파일이나 엉뚱한 버전을 읽지 않는다."""
        sfbackend.check_key(key)
        f = self.dir / "objects" / f"{key}@{safe_part(etag)}"
        try:
            return f.read_bytes()
        except FileNotFoundError:
            pass
        r = self.be.get(key)
        if r is None:
            raise sfbackend.BackendError(f"{key} 가 그사이 사라졌다")
        data, got = r
        f = self.dir / "objects" / f"{key}@{safe_part(got)}"
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f".tmp-{os.getpid()}-{os.urandom(4).hex()}")
        tmp.write_bytes(data)
        os.replace(tmp, f)
        name = key.rsplit("/", 1)[-1]
        for old in f.parent.glob(f"{glob_escape(name)}@*"):  # 같은 key 의 예전 버전
            if old != f:
                with contextlib.suppress(OSError):
                    old.unlink()
        return data

    def sessions(self, repo_key, tool=None) -> list:
        """meta 목록 (최근 갱신 순). repo_key 가 None 이면 모든 저장소."""
        keys = self.be.list(f"logs/{repo_key}/" if repo_key else "logs/")
        by_dir = {}
        for k, etag in keys.items():
            d, _, name = k.rpartition("/")
            by_dir.setdefault(d, {})[name] = etag
        out = []
        for d, files in by_dir.items():
            if "meta.json" not in files:
                continue
            try:
                meta = json.loads(self.fetch(f"{d}/meta.json", files["meta.json"]))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict) or (tool and meta.get("tool") != tool):
                continue
            meta["_dir"], meta["_files"] = d, files
            out.append(meta)
        out.sort(key=lambda m: instant(m.get("updated")), reverse=True)
        return out

    def raw(self, meta: dict) -> bytes:
        """올라간 기록 원본(가린 뒤). meta 에 붙여 두지 않는다 — search 가 세션을 훑는 동안 쌓이지 않게."""
        files, d = meta["_files"], meta["_dir"]
        fmt = meta.get("format") or ""
        if fmt == "markdown":
            data = self.fetch(f"{d}/transcript.md", files["transcript.md"])
        elif fmt == "json-snapshot":
            data = gzip.decompress(self.fetch(f"{d}/transcript.json.gz", files["transcript.json.gz"]))
        else:
            segs = sorted(n for n in files if re.fullmatch(r"\d{6}\.jsonl\.gz", n))
            data = b"".join(gzip.decompress(self.fetch(f"{d}/{n}", files[n])) for n in segs)
        return data

    def events(self, meta: dict) -> list:
        return events_from(meta.get("tool") or "", meta.get("format") or "", self.raw(meta))


def open_remote(a):
    be = sfstate.load_backend()
    if not be:
        print("LOG=off (backend 가 없다 — sfstate.py init --backend … 로 정한다)")
        sys.exit(1)
    remote = Remote(be)
    repo_key = None
    if not a.all_repos:
        ctx = sfstate.Ctx(a.dir)
        repo_key = ctx.repo_key or "_norepo"
    return remote, repo_key


def find_session(remote, repo_key, wanted: str):
    metas = remote.sessions(repo_key)
    hits = [m for m in metas if str(m.get("session_id", "")).startswith(wanted)
            or m["_dir"].rsplit("/", 1)[-1].startswith(wanted)]
    exact = [m for m in hits if m.get("session_id") == wanted]
    if exact:
        return exact[0]
    if len(hits) == 1:
        return hits[0]
    where = "모든 저장소" if repo_key is None else repo_key
    if not hits:
        print(f"SHOW=none ({where} 에 '{wanted}' 로 시작하는 세션이 없다 — 다른 저장소면 --all-repos)")
    else:
        print(f"SHOW=ambiguous ({len(hits)}개) — 더 길게 적는다:")
        for m in hits[:20]:
            print(f"  {m.get('session_id')}  {m.get('tool')}  {m.get('updated')}  {m.get('title') or ''}")
    sys.exit(1)


def meta_line(m: dict) -> str:
    seg = m.get("segments") or (1 if m.get("format") in ("json-snapshot", "markdown") else 0)
    where = "" if m.get("_repo_shown") else f"{m.get('repo_key') or '_norepo'} · "
    return (f"{(m.get('updated') or '')[:16]}  {m.get('tool', '?'):<6}  {m.get('session_id')}  "
            f"{where}{m.get('branch') or '-'} · {m.get('host') or '-'} · {seg}seg"
            + (" · 진행 중" if not m.get("ended") else "") + (f"\n    {m['title']}" if m.get("title") else ""))


def cmd_list(a):
    remote, repo_key = open_remote(a)
    metas = remote.sessions(repo_key, a.tool)[:a.limit]
    if a.json:
        print(json.dumps([{k: v for k, v in m.items() if not k.startswith("_")} for m in metas],
                         ensure_ascii=False))
        return
    print(f"LOGS={repo_key or '(모든 저장소)'} · {len(metas)}개")
    for m in metas:
        m["_repo_shown"] = repo_key is not None
        print(meta_line(m))


def cmd_show(a):
    remote, repo_key = open_remote(a)
    meta = find_session(remote, repo_key, a.session)
    data = remote.raw(meta)
    events = events_from(meta.get("tool") or "", meta.get("format") or "", data)
    if a.raw:
        body = data.decode("utf-8", "replace")
    else:
        head = (f"# {meta.get('tool')} · {meta.get('session_id')}\n\n"
                f"> repo: {meta.get('repo_key') or '-'} · branch: {meta.get('branch') or '-'} · "
                f"host: {meta.get('host') or '-'}\n> {meta.get('started') or '?'} → "
                f"{meta.get('ended') or meta.get('updated') or '진행 중'}\n\n")
        body = head + render(events, tools=not a.no_tools, full=a.full)
    if a.out:
        Path(a.out).expanduser().write_text(body, encoding="utf-8")
        turns = sum(1 for e in events if e["role"] == "user")
        print(f"SHOW={a.out} ({meta.get('session_id')} · 사용자 말 {turns}개 · {len(body)}자)")
    else:
        sys.stdout.write(body)


def cmd_search(a):
    remote, repo_key = open_remote(a)
    since = dt.datetime.now().astimezone() - dt.timedelta(days=a.days)
    pat = re.compile(a.query if a.regex else re.escape(a.query), re.I)
    hits = 0
    for m in remote.sessions(repo_key, a.tool):
        if instant(m.get("updated")) < since:
            continue
        found = []
        for e in remote.events(m):
            for mt in pat.finditer(e["text"]):
                lo, hi = max(0, mt.start() - 80), min(len(e["text"]), mt.end() + 80)
                snippet = e["text"][lo:hi].replace("\n", " ")
                found.append(f"    [{e['role']}{'·' + e['name'] if e['name'] else ''}] …{snippet}…")
                break
            if len(found) >= 5:
                break
        if found:
            m["_repo_shown"] = repo_key is not None
            print(meta_line(m))
            print("\n".join(found))
            hits += 1
            if hits >= a.limit:
                break
    print(f"SEARCH={hits}개 세션 (최근 {a.days}일, {repo_key or '모든 저장소'})")


def cmd_save(a):
    be = sfstate.load_backend()
    if not be:
        print("SAVE=off (backend 가 없다 — sfstate.py init --backend … 로 정한다)")
        sys.exit(1)
    be.identity()
    text = Path(a.file).expanduser().read_text(encoding="utf-8") if a.file else sys.stdin.read()
    if not text.strip():
        print("SAVE=empty (남길 내용이 없다)")
        sys.exit(1)
    extra = user_patterns()
    ctx = sfstate.Ctx(a.dir)
    host = socket.gethostname().split(".")[0]
    sid = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{safe_part(host)}-{os.urandom(2).hex()}"
    prefix = f"logs/{ctx.repo_key or '_norepo'}/manual/{sid}"
    now = now_iso()
    be.put(f"{prefix}/transcript.md", scrub_text(text, extra).encode("utf-8", "surrogateescape"), if_none_match=True)
    meta = {"tool": "manual", "session_id": sid, "repo_key": ctx.repo_key, "branch": ctx.branch,
            "cwd": str(ctx.cwd), "host": host, "format": "markdown", "segments": 1, "rewrites": 0,
            "started": now, "updated": now, "ended": now, "title": utf8(scrub_text(a.title, extra)[:100])}
    be.put(f"{prefix}/meta.json", json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))
    print(f"SAVED={sid} ({prefix})")


def main(argv=None):
    p = argparse.ArgumentParser(prog="sflog", description="코딩 에이전트 transcript 를 backend 에 모은다")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("collect")
    sp.add_argument("--tool", choices=TOOLS, required=True)
    sp.add_argument("--session", required=True)
    sp.add_argument("--transcript", default="")
    sp.add_argument("--cwd", default="")
    sp.add_argument("--final", action="store_true")
    sp.set_defaults(fn=cmd_collect)

    def where(sp):
        sp.add_argument("--dir", default=None, help="저장소 (기본: 현재 cwd)")
        sp.add_argument("--all-repos", action="store_true", help="모든 저장소의 기록")
        return sp

    sp = where(sub.add_parser("list"))
    sp.add_argument("--tool", choices=(*TOOLS, "manual"))
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_list)
    sp = where(sub.add_parser("show"))
    sp.add_argument("session")
    sp.add_argument("--no-tools", action="store_true", help="도구 호출·결과를 빼고 대화만")
    sp.add_argument("--full", action="store_true", help="도구 입력·결과를 자르지 않는다")
    sp.add_argument("--raw", action="store_true", help="올라간 원본 그대로 (가린 뒤)")
    sp.add_argument("--out", default="", help="화면 대신 파일에 쓴다")
    sp.set_defaults(fn=cmd_show)
    sp = where(sub.add_parser("search"))
    sp.add_argument("query")
    sp.add_argument("--days", type=int, default=30)
    sp.add_argument("--tool", choices=(*TOOLS, "manual"))
    sp.add_argument("--regex", action="store_true")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(fn=cmd_search)
    sp = sub.add_parser("save")
    sp.add_argument("--title", required=True)
    sp.add_argument("--dir", default=None)
    sp.add_argument("--file", default="")
    sp.set_defaults(fn=cmd_save)
    a = p.parse_args(argv)
    try:
        a.fn(a)
    except sfbackend.BackendError as e:  # 원격에 닿지 못했거나 저장소 키가 없다 — traceback 대신 사유만
        print(f"{a.cmd.upper()}=failed ({e})")
        sys.exit(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
