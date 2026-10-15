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

서브커맨드:
  collect --tool T --session S [--transcript P] [--cwd D] [--final]
          한 세션의 새 내용을 올린다. backend 가 없으면 아무것도 하지 않는다.
          --final: 세션 끝 — 마지막 줄이 줄바꿈 없이 끝나도 올린다.

비밀값 가리기: 아래 SECRET_PATTERNS + ~/.hbrness/redact.txt (한 줄에 정규식 하나, # 주석).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
import re
import socket
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
    ("aws-access-key", re.compile(B + r"(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(B + r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("anthropic-key", re.compile(B + r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-key", re.compile(B + r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("slack-token", re.compile(B + r"xox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("google-api-key", re.compile(B + r"AIza[0-9A-Za-z_\-]{35}")),
    ("atlassian-token", re.compile(B + r"ATATT[A-Za-z0-9_\-=]{20,}")),
    ("jwt", re.compile(B + r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("bearer", re.compile(r"(?i)" + B + r"bearer\s+[A-Za-z0-9._~+/=\-]{16,}")),
]
_SENSITIVE = (r"password|passwd|secret|secret[_-]?access[_-]?key|api[_-]?key|access[_-]?token|auth[_-]?token"
              r"|client[_-]?secret|token")
# 글 속의 `password=…`, `DB_PASSWORD="two words"`, `"api_key": "…"` 꼴은 값만 가린다. 따옴표로 묶인 값은
# 닫는 따옴표까지 통째로(짧아도, 공백이 있어도), 안 묶인 값은 공백·구분자 전까지.
ASSIGNMENT = re.compile(
    r"(?i)" + B + r"((?:[A-Za-z0-9]{1,32}[_-]){0,4}(?:" + _SENSITIVE + r"))"  # 접두어 반복에 상한 — 긴 base64 에서 느려지지 않게
    r"(\\?[\"']?\s*[:=]\s*)"
    r"(\\\"(?:(?!\\\").)*\\\"|\"[^\"\n]*\"|'[^'\n]*'|[^\s\"'\\,;}&)]+)")
# JSON 객체에서 이름이 이런 key 의 값(문자열·숫자)은 통째로 가린다. 예: {"db_password": 123456789}
SENSITIVE_KEY = re.compile(r"(?i)^(?:.*[_-])?(?:" + _SENSITIVE + r")$")
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
            return f"{m.group(1)}{m.group(2)}{q}{MASK}{q}"
    return f"{m.group(1)}{m.group(2)}{MASK}"


def redact_text(text: str, extra=()) -> str:
    for name, pat in [*SECRET_PATTERNS, *extra]:
        text = pat.sub(f"[REDACTED:{name}]", text)
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
    return json.dumps(new, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if changed else data


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
        be.put(f"{prefix}/{seq:06d}.jsonl.gz", gzip.compress(redact_jsonl(chunk, extra), mtime=0))
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
    be.put(f"{prefix}/transcript.json.gz", gzip.compress(redact_json_bytes(data, extra), mtime=0))
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
    a = p.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
