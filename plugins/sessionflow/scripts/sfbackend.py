#!/usr/bin/env python3
"""sfbackend — sessionflow state 를 원격 key-value 저장소(backend)에 두고, 로컬 state 디렉토리를 그 캐시로 맞춘다.

Terraform 의 backend 와 같은 구조다. 원격은 key → 내용 저장소이고, 로컬 state 디렉토리
(기본 ~/.hbrness/state)는 원격의 사본이다. 마지막으로 맞춘 원격 버전(etag)과 그때의 내용
해시는 <state>/.sfstate/manifest.json 에 적어 둔다.

  원격 key              repos/<로컬 state 기준 상대경로>   예: repos/github.com/o/r/followups/x.md
  pull                  원격 목록을 받아 manifest 와 etag 가 다른 것만 내려받는다.
  push(prefix)          로컬에서 바뀐 파일만 conditional write 로 올린다.
                        이미 있던 파일은 If-Match(manifest 의 etag), 새 파일은 If-None-Match.
  충돌                  다른 PC 가 같은 파일을 먼저 바꿨으면 원격본을 원래 자리에 받고,
                        이 PC 의 버전은 <state>/_conflicts/ 에 남긴다.
  삭제                  지운 파일은 object 를 지우지 않고 tombstone 으로 덮어쓴다 (If-Match PUT).
                        DeleteObject 의 If-Match 를 무시하는 저장소(MinIO 등)에서도 그사이 다른 PC 가
                        고친 버전을 지우지 않는다. pull 은 tombstone 을 삭제로 읽고, 그 자리에 다시 만든
                        파일은 tombstone 의 etag 로 If-Match PUT 한다. tombstone 은 지우지 않는다 (작다).

동기화하지 않는 것: 최상위의 '_'·'.' 로 시작하는 디렉토리(_local, _conflicts, .sfstate, .git),
최상위 파일(README.md 등), INDEX.md(각 PC 가 다시 만드는 생성물), '.' 로 시작하는 파일.

설정 파일(backend.json):
  {"type": "local", "path": "/some/dir"}   디렉토리 하나를 원격처럼 쓴다 (테스트·오프라인용)
  {"type": "s3", "endpoint": "https://…", "bucket": "b", "prefix": "hbrness/", "region": "auto",
   "path_style": true}                     S3 API 를 쓰는 저장소 (AWS S3·R2·MinIO 등). SigV4 서명을 직접 한다.

s3 자격증명 {"access_key_id": "…", "secret_access_key": "…", "session_token": "…(선택)"} 은 backend.json 의
"credentials" 가 정한 곳에 둔다:
  keychain      macOS Keychain (security CLI, 서비스 hbrness-sfstate). 비밀값은 stdin 으로만 넘긴다.
  secret-tool   Linux Secret Service (libsecret 의 secret-tool). 비밀값은 stdin 으로만 넘긴다.
  file          backend.json 옆의 credentials.json (mode 600). 값이 없으면 이것.
환경변수 HBRNESS_S3_ACCESS_KEY_ID 와 HBRNESS_S3_SECRET_ACCESS_KEY 가 둘 다 있으면 (HBRNESS_S3_SESSION_TOKEN 과 함께)
한 묶음으로 그쪽을 먼저 쓴다. 저장된 값과 섞지 않는다.

저장소마다 표시 object(<prefix>.sfbackend, local 은 <dir>/.sfbackend)에 저장소 ID 를 적어 둔다.
표시가 없으면 원격에 닿지 못한 것으로 보고 실패한다. manifest 는 이 ID 에 묶인다.
  {"id": "<uuid>", "encryption": {"type": "age", "recipients": ["age1…"]}}   (1.2 까지는 ID 한 줄)

암호화: 저장소를 만들 때(init) 표시에 age 공개키를 적으면 그 저장소의 object 는 모두 age 로 암호화해 올리고
풀어서 읽는다 (표시만 평문). 암호화는 공개키로 하고, 푸는 키는 backend.json 옆의 age.key(mode 600)에 둔다 —
자격증명처럼 PC 마다 한 번 복사한다. init 이 같은 설정을 backend.json 의 "encryption" 에도 적고, 이후에는
매번 표시와 맞춰 본다. 누가 표시를 고쳐 암호화를 빼거나 공개키를 바꿔치기하면 올리지 않고 실패한다.
"""

from __future__ import annotations

import contextlib
import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
import hmac
import http.client
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

REMOTE_PREFIX = "repos/"
CONFLICT_DIR = "_conflicts"
META_DIR = ".sfstate"
SKIP_FILES = {"INDEX.md"}
TOMBSTONE = b"\0sfstate-tombstone\n"  # 지운 파일 자리에 남기는 object 의 첫 줄 (글 파일에는 NUL 이 없다)
AGE_MAGIC = b"age-encryption.org/"  # age 로 암호화한 내용의 첫 줄
AGE_RECIPIENT = re.compile(r"age1[0-9a-z]{20,}")
# GUI 로 띄운 에이전트의 훅은 PATH 가 짧다 — PATH 에 없으면 흔한 설치 자리도 본다
TOOL_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin")


class BackendError(Exception):
    """원격 저장소에 닿지 못했거나 설정이 잘못됐다."""


class PreconditionFailed(BackendError):
    """If-Match / If-None-Match 조건이 맞지 않아 원격이 쓰기를 거절했다."""


class PartialSync(BackendError):
    """pull/push 가 중간에 실패했다. report 에 그때까지 한 일(특히 conflicts)이 들어 있다."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_key(key: str):
    parts = key.split("/")
    if not key or key.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise BackendError(f"잘못된 key: {key!r}")


def which(name: str):
    return shutil.which(name) or next((f"{d}/{name}" for d in TOOL_DIRS if os.access(f"{d}/{name}", os.X_OK)), None)


# ─────────────────────────────────────────────────────────────────────────────
# 저장소 표시 · 암호화
# ─────────────────────────────────────────────────────────────────────────────

def new_marker(encryption=None) -> bytes:
    doc = {"id": uuid.uuid4().hex}
    if encryption:
        doc["encryption"] = encryption
    return (json.dumps(doc) + "\n").encode()


def parse_marker(raw: bytes) -> dict:
    """저장소 표시 → {"id", "encryption"(있으면)}. 1.2 까지 만든 표시는 ID 한 줄이다."""
    text = raw.decode("utf-8", "replace").strip()
    doc = None
    if text.startswith("{"):
        with contextlib.suppress(ValueError):
            doc = json.loads(text)
    elif text:
        doc = {"id": text.splitlines()[0].strip()}
    if not isinstance(doc, dict) or not isinstance(doc.get("id"), str) or not doc["id"]:
        raise BackendError(f"저장소 표시({text[:60]!r})를 읽지 못했다 — init 을 다시 한다")
    return doc


def run_tool(args, data: bytes = b"") -> bytes:
    exe = which(args[0])
    if not exe:
        raise BackendError(f"{args[0]} 가 없다 — age 를 설치한다 (brew install age · apt install age)")
    try:
        p = subprocess.run([exe, *args[1:]], input=data, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise BackendError(f"{args[0]} 를 돌리지 못했다: {e}") from None
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        raise BackendError(f"{args[0]}: {err[0] if err else f'exit {p.returncode}'}")
    return p.stdout


def public_keys(key_path: Path) -> list:
    return run_tool(["age-keygen", "-y", str(key_path)]).decode().split()


def make_key(key_path: Path) -> str:
    """age.key 가 없으면 만든다 (age-keygen 이 mode 600 으로 쓰고, 있는 파일은 덮어쓰지 않는다). 반환: 공개키."""
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        run_tool(["age-keygen", "-o", str(key_path)])
    keys = public_keys(key_path)
    if not keys:
        raise BackendError(f"{key_path} 에 age 키가 없다")
    return keys[0]


class Age:
    """age CLI 로 object 내용을 암호화한다. 암호화는 표시에 적힌 공개키로만 하므로 키를 아직 복사하지 않은 PC 도
    올릴 수는 있고, 읽을 때 이 PC 의 age.key 가 필요하다."""

    def __init__(self, encryption, key_path: Path | None):
        enc = encryption if isinstance(encryption, dict) else {}
        recipients = enc.get("recipients")
        if enc.get("type") != "age" or not isinstance(recipients, list) or not recipients or not all(
                isinstance(r, str) and AGE_RECIPIENT.fullmatch(r) for r in recipients):
            raise BackendError(f"모르는 암호화 설정: {encryption!r}")
        self.recipients = recipients
        self.key_path = key_path
        self._key_ok = False

    def seal(self, data: bytes) -> bytes:
        args = ["age"]
        for r in self.recipients:
            args += ["-r", r]
        return run_tool(args, data)

    def check_key(self):
        """이 PC 의 키가 있고 저장소 공개키와 짝이 맞는지. 아니면 할 일을 적은 BackendError."""
        if self._key_ok:
            return
        if self.key_path is None or not self.key_path.is_file():
            raise BackendError(f"이 저장소는 age 로 암호화돼 있는데 이 PC 에 키({self.key_path or 'age.key'})가 없다 — "
                               "저장소를 만든 PC 의 age.key 를 같은 자리에 복사한다 (mode 600)")
        if not set(public_keys(self.key_path)) & set(self.recipients):
            raise BackendError(f"{self.key_path} 는 이 저장소의 키가 아니다 (저장소 공개키: {', '.join(self.recipients)})"
                               " — 저장소를 만든 PC 의 age.key 로 바꾼다")
        self._key_ok = True

    def open(self, data: bytes, key: str) -> bytes:
        self.check_key()
        try:
            return run_tool(["age", "-d", "-i", str(self.key_path)], data)
        except BackendError as e:
            raise BackendError(f"{key} 를 풀지 못했다 ({e})") from None


# ─────────────────────────────────────────────────────────────────────────────
# backend
# ─────────────────────────────────────────────────────────────────────────────

class Backend:
    """LocalBackend·S3Backend 공통. 저장소 표시를 읽고, 표시가 age 암호화를 정했으면 object 를 암호화해 올리고
    풀어서 읽는다. 각 backend 는 내용을 그대로 다루는 read_marker / get_raw / put_raw 를 만든다."""

    MARKER = ".sfbackend"
    encryption = None  # backend.json 의 "encryption" — 표시와 다르면 쓰지도 읽지도 않는다
    key_path = None    # 푸는 키 (age.key)
    _marker = None
    _cipher = None

    def marker(self) -> dict:
        """표시는 명령 하나에서 한 번만 읽는다 — put/get 마다 다시 받지 않게."""
        if self._marker is None:
            raw = self.read_marker()
            if raw is None:
                raise BackendError(f"{self.describe()} 에 저장소 표시({self.MARKER})가 없다 — "
                                   "옮겼거나 지웠으면 init 을 다시 한다")
            self._marker = parse_marker(raw)
        return self._marker

    def identity(self) -> str:
        """manifest 가 가리키는 저장소. 같은 자리라도 저장소를 새로 만들었으면 달라진다."""
        return f"{self.describe()}#{self.marker()['id']}"

    def cipher(self):
        """이 저장소의 암호화. 없으면 None."""
        declared = self.marker().get("encryption")
        if declared != self.encryption:
            if not self.encryption:
                raise BackendError("저장소가 age 로 암호화돼 있는데 이 PC 의 backend.json 에는 그 설정이 없다 — "
                                   "init 을 다시 한다 (저장소를 만든 PC 의 age.key 를 먼저 복사한다)")
            raise BackendError("저장소 표시의 암호화 설정이 이 PC 의 backend.json 에 적어 둔 것과 다르다 — 누가 왜 "
                               "바꿨는지 확인한다. 맞게 바꾼 것이면 init --accept-encryption-change 로 다시 한다")
        if declared and self._cipher is None:
            self._cipher = Age(declared, self.key_path)
        return self._cipher

    def put(self, key: str, data: bytes, if_match: str | None = None, if_none_match: bool = False) -> str:
        c = self.cipher()
        return self.put_raw(key, c.seal(data) if c else data, if_match=if_match, if_none_match=if_none_match)

    def get(self, key: str):
        """(내용, etag) 또는 None. etag 는 올라간 그대로(암호문)의 것이다. 암호화한 저장소에서 암호문이 아닌
        object 는 받지 않는다 — 망가졌거나 누가 넣은 내용이 로컬 사본을 덮지 않게."""
        r = self.get_raw(key)
        c = self.cipher() if r else None
        if not c:
            return r
        if not r[0].startswith(AGE_MAGIC):
            raise BackendError(f"{key} 가 암호문이 아니다 — 암호화한 저장소에 평문 object 가 있다 "
                               "(망가졌거나 누가 넣었는지 확인한다)")
        return c.open(r[0], key), r[1]


class LocalBackend(Backend):
    """디렉토리 하나를 원격처럼 쓴다. etag 는 내용의 sha256 이다.
    conditional write 는 디렉토리의 .lock 을 flock 으로 잡고 확인과 쓰기를 한 번에 한다.
    init 이 표시 파일(.sfbackend)을 만들고 저장소 ID 를 적는다. 표시 파일이 없으면 디렉토리가 옮겨졌거나
    빠진 것으로 보고 실패한다 — 빈 목록으로 읽으면 pull 이 로컬 사본을 전부 지운다. 같은 경로에 저장소를
    새로 만들면 ID 가 달라져서 예전 manifest 를 버린다 (identity)."""

    def __init__(self, path):
        self.root = Path(path).expanduser()

    def describe(self) -> str:
        return location({"type": "local", "path": str(self.root)})

    def ensure(self, encryption=None) -> dict:
        """init 에서만 부른다. 원격 디렉토리를 만들고, 표시 파일이 없으면 새 저장소로 만든다. 반환: 표시 내용."""
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root / self.MARKER
        # 두 PC 가 같은 때 만들어도 표시는 하나다 — 먼저 만든 쪽의 ID·공개키를 둘 다 쓴다
        with open(self.root / ".lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                if not marker.is_file() or not marker.read_bytes().strip():
                    tmp = marker.with_name(f".tmp-{os.getpid()}-{self.MARKER}")
                    tmp.write_bytes(new_marker(encryption))
                    os.replace(tmp, marker)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        self._marker = self._cipher = None
        return self.marker()

    def _check(self):
        if not (self.root / self.MARKER).is_file():
            raise BackendError(f"원격 디렉토리 {self.root} 에 닿을 수 없다 (옮겼거나 빠졌으면 init 을 다시 한다)")

    def read_marker(self):
        try:
            return (self.root / self.MARKER).read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            return None

    @contextlib.contextmanager
    def _lock(self):
        self._check()
        with open(self.root / ".lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _path(self, key: str) -> Path:
        check_key(key)
        return self.root / key

    def list(self, prefix: str) -> dict:
        self._check()
        base = self.root / prefix
        if not base.is_dir():
            return {}
        out = {}
        for f in base.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                out[f.relative_to(self.root).as_posix()] = sha256(f.read_bytes())
        return out

    def get_raw(self, key: str):
        self._check()
        try:
            data = self._path(key).read_bytes()
        except FileNotFoundError:
            return None
        return data, sha256(data)

    def stat(self, key: str):
        r = self.get_raw(key)
        return r[1] if r else None

    def put_raw(self, key: str, data: bytes, if_match: str | None = None, if_none_match: bool = False) -> str:
        p = self._path(key)
        with self._lock():
            cur = self.stat(key)
            if if_none_match and cur is not None:
                raise PreconditionFailed(key)
            if if_match is not None and cur != if_match:
                raise PreconditionFailed(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(f".tmp-{os.getpid()}-{p.name}")
            tmp.write_bytes(data)
            os.replace(tmp, p)
        return sha256(data)

    def delete(self, key: str, if_match: str | None = None) -> bool:
        """지웠으면 True, 이미 없었으면 False. if_match 가 현재 etag 와 다르면 PreconditionFailed."""
        p = self._path(key)
        with self._lock():
            cur = self.stat(key)
            if cur is None:
                return False
            if if_match is not None and cur != if_match:
                raise PreconditionFailed(key)
            p.unlink()
            _prune_empty(p.parent, self.root)
            return True


class S3Backend(Backend):
    """S3 API 저장소. ETag 를 etag 로 쓰고, PutObject 의 If-Match / If-None-Match 로 conditional write 를 한다.
    DeleteObject 는 If-Match 를 보내되, 지원하지 않는 저장소도 있어 HEAD 로 먼저 etag 를 확인한다."""

    TIMEOUT = 30
    page_size = None  # ListObjectsV2 max-keys. None 이면 저장소 기본값(보통 1000). 테스트가 줄인다.

    def __init__(self, cfg: dict, creds: dict):
        for k in ("bucket",):
            if not cfg.get(k):
                raise BackendError(f"s3 backend 에 {k} 가 없다")
        if not creds.get("access_key_id") or not creds.get("secret_access_key"):
            raise BackendError("s3 자격증명이 없다 — credentials.json 이나 HBRNESS_S3_* 환경변수를 확인한다")
        self.bucket = cfg["bucket"]
        prefix = (cfg.get("prefix") or "").strip("/")
        self.prefix = prefix + "/" if prefix else ""
        self.region = cfg.get("region") or "us-east-1"
        u = s3_endpoint(cfg)
        self.scheme = u.scheme
        self.base_path = u.path.rstrip("/")
        self.path_style = bool(cfg.get("path_style", bool(cfg.get("endpoint"))))
        self.host = u.netloc if self.path_style else f"{self.bucket}.{u.netloc}"
        self.endpoint = f"{u.scheme}://{u.netloc}{self.base_path}"
        self.creds = creds
        self._location = location({**cfg, "type": "s3"})

    def describe(self) -> str:
        return self._location

    # ── 서명·요청 ──────────────────────────────────────────────────────────

    def _path(self, key: str = "") -> str:
        segs = [self.bucket] if self.path_style else []
        if key:
            segs.append(key)
        return self.base_path + "/" + urllib.parse.quote("/".join(segs), safe="/-_.~")

    @staticmethod
    def _query(params: dict) -> str:
        q = lambda v: urllib.parse.quote(str(v), safe="-_.~")
        return "&".join(f"{q(k)}={q(v)}" for k, v in sorted(params.items()))

    def _sign(self, method: str, path: str, query: str, payload_hash: str, now: dt.datetime) -> dict:
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date = amz_date[:8]
        headers = {"host": self.host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
        if self.creds.get("session_token"):
            headers["x-amz-security-token"] = self.creds["session_token"]
        names = sorted(headers)
        canonical = "\n".join([method, path, query,
                               "".join(f"{n}:{headers[n].strip()}\n" for n in names),
                               ";".join(names), payload_hash])
        scope = f"{date}/{self.region}/s3/aws4_request"
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                             hashlib.sha256(canonical.encode()).hexdigest()])
        k = ("AWS4" + self.creds["secret_access_key"]).encode()
        for part in (date, self.region, "s3", "aws4_request"):
            k = hmac.new(k, part.encode(), hashlib.sha256).digest()
        sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
        headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={self.creds['access_key_id']}/{scope}, "
                                    f"SignedHeaders={';'.join(names)}, Signature={sig}")
        del headers["host"]  # urllib 이 URL 로 같은 값을 넣는다
        return headers

    def _request(self, method: str, key: str = "", params=None, body: bytes = b"", extra=None):
        """반환: (status, headers, body). 4xx/5xx 도 그대로 돌려준다. 네트워크 실패는 BackendError."""
        path = self._path(key)
        query = self._query(params or {})
        headers = self._sign(method, path, query, hashlib.sha256(body).hexdigest(),
                             dt.datetime.now(dt.timezone.utc))
        headers.update(extra or {})
        url = f"{self.scheme}://{self.host}{path}" + (f"?{query}" if query else "")
        req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None,
                                     method=method, headers=headers)
        # 응답을 읽다 연결이 끊기면(IncompleteRead 등) 그것도 BackendError 로 바꾼다 — 그래야 Cache 가
        # PartialSync 로 감싸 그때까지의 충돌을 알린다.
        try:
            try:
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as r:
                    return r.status, r.headers, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.headers, e.read() if method != "HEAD" else b""
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            raise BackendError(f"{self.endpoint} 에 닿지 못했다: {getattr(e, 'reason', None) or e!r}") from e

    @staticmethod
    def _error(status: int, body: bytes, what: str) -> BackendError:
        code = msg = ""
        try:
            root = ET.fromstring(body)
            code = root.findtext("Code") or ""
            msg = root.findtext("Message") or ""
        except ET.ParseError:
            pass
        return BackendError(f"{what}: HTTP {status} {code} {msg}".strip())

    @staticmethod
    def _etag(headers) -> str:
        return (headers.get("ETag") or "").strip('"')

    # ── backend 인터페이스 ─────────────────────────────────────────────────

    def ensure(self, encryption=None) -> dict:
        """init 에서만 부른다. bucket 에 닿는지 보고, 표시 object 가 없으면 새 저장소로 만든다. 반환: 표시 내용.
        같은 때 다른 PC 가 먼저 만들었으면 그쪽 표시가 남는다."""
        self.list("", limit=1)
        try:
            self._put_full(self.prefix + self.MARKER, new_marker(encryption), if_none_match=True)
        except PreconditionFailed:
            pass
        self._marker = self._cipher = None
        return self.marker()

    def read_marker(self):
        r = self._get_full(self.prefix + self.MARKER)
        return r[0] if r else None

    def list(self, prefix: str, limit: int | None = None) -> dict:
        out, token = {}, None
        full = self.prefix + prefix
        while True:
            params = {"list-type": "2", "prefix": full}
            if limit or self.page_size:
                params["max-keys"] = str(limit or self.page_size)
            if token:
                params["continuation-token"] = token
            status, _, body = self._request("GET", params=params)
            if status != 200:
                raise self._error(status, body, f"목록 {full}")
            # 목록이 모자라면 pull 이 빠진 파일을 '원격에서 지웠다' 로 읽고 로컬 사본을 지운다.
            # 그래서 모양이 이상한 응답은 빈 목록이 아니라 실패로 본다.
            try:
                root = ET.fromstring(body)
            except ET.ParseError as e:
                raise BackendError(f"목록 {full}: 응답을 읽지 못했다 ({e})") from e
            for el in root.iter():
                el.tag = el.tag.rsplit("}", 1)[-1]  # namespace 떼기
            truncated = root.findtext("IsTruncated")
            if root.tag != "ListBucketResult" or truncated not in ("true", "false"):
                raise BackendError(f"목록 {full}: ListObjectsV2 응답이 아니다 ({root.tag}, IsTruncated={truncated!r})")
            for c in root.findall("Contents"):
                k = c.findtext("Key") or ""
                etag = (c.findtext("ETag") or "").strip('"')
                if not k or not etag:
                    raise BackendError(f"목록 {full}: Key 나 ETag 가 빠진 항목이 있다")
                if k.startswith(self.prefix):
                    out[k[len(self.prefix):]] = etag
            if limit or truncated == "false":
                return out
            token = root.findtext("NextContinuationToken")
            if not token:
                raise BackendError(f"목록 {full}: 다음 페이지가 있다는데 NextContinuationToken 이 없다")

    def _get_full(self, full_key: str):
        status, headers, body = self._request("GET", full_key)
        if status == 404:
            return None
        if status != 200:
            raise self._error(status, body, f"읽기 {full_key}")
        return body, self._etag(headers)

    def get_raw(self, key: str):
        check_key(key)
        return self._get_full(self.prefix + key)

    def stat(self, key: str):
        check_key(key)
        status, headers, body = self._request("HEAD", self.prefix + key)
        if status == 404:
            return None
        if status != 200:
            raise self._error(status, body, f"확인 {key}")
        return self._etag(headers)

    def _put_full(self, full_key: str, data: bytes, if_match=None, if_none_match=False) -> str:
        extra = {"Content-Type": "application/octet-stream"}
        if if_none_match:
            extra["If-None-Match"] = "*"
        if if_match is not None:
            extra["If-Match"] = f'"{if_match}"'
        status, headers, body = self._request("PUT", full_key, body=data, extra=extra)
        if status in (200, 201):
            return self._etag(headers)
        # 412: 조건 불일치 · 409: 동시에 다른 conditional write 가 진행 중 · 404: If-Match 대상이 없음
        if status == 412 or (status in (404, 409) and (if_match is not None or if_none_match)):
            raise PreconditionFailed(full_key)
        raise self._error(status, body, f"쓰기 {full_key}")

    def put_raw(self, key: str, data: bytes, if_match: str | None = None, if_none_match: bool = False) -> str:
        check_key(key)
        return self._put_full(self.prefix + key, data, if_match=if_match, if_none_match=if_none_match)

    def delete_request(self, key: str, if_match: str | None = None) -> int:
        """DeleteObject 를 그대로 보낸다 (doctor 가 If-Match 지원을 확인할 때 쓴다). 반환: HTTP status."""
        check_key(key)
        extra = {"If-Match": f'"{if_match}"'} if if_match is not None else {}
        status, _, body = self._request("DELETE", self.prefix + key, extra=extra)
        if status not in (200, 204, 404, 412):
            raise self._error(status, body, f"지우기 {key}")
        return status

    def delete(self, key: str, if_match: str | None = None) -> bool:
        cur = self.stat(key)
        if cur is None:
            return False
        if if_match is not None and cur != if_match:
            raise PreconditionFailed(key)
        status = self.delete_request(key, if_match)
        if status == 412:
            raise PreconditionFailed(key)
        return status != 404

    def lifecycle_rules(self) -> list:
        """bucket lifecycle 규칙. 대화 기록(logs/) 보관 기간을 확인할 때 쓴다. 규칙이 없으면 빈 목록.
        반환: [{"prefix", "enabled", "expires", "filtered"}] — filtered 는 태그·크기 조건이 붙어 일부에만 걸린다는 뜻."""
        status, _, body = self._request("GET", params={"lifecycle": ""})
        if status == 404:
            return []
        if status != 200:
            raise self._error(status, body, "lifecycle 확인")
        root = _xml(body, "lifecycle 확인")
        for el in root.iter():
            el.tag = el.tag.rsplit("}", 1)[-1]
        out = []
        for rule in root.findall("Rule"):
            prefix = next((rule.findtext(q) for q in ("Filter/Prefix", "Filter/And/Prefix", "Prefix")
                           if rule.find(q) is not None), "")
            out.append({
                "prefix": prefix or "",
                "enabled": (rule.findtext("Status") or "") == "Enabled",
                "expires": bool(rule.findtext("Expiration/Days") or rule.findtext("Expiration/Date")),
                "filtered": any(rule.find(q) is not None for q in (
                    "Filter/Tag", "Filter/And/Tag", "Filter/ObjectSizeGreaterThan", "Filter/ObjectSizeLessThan",
                    "Filter/And/ObjectSizeGreaterThan", "Filter/And/ObjectSizeLessThan")),
            })
        return out

    def versioning(self) -> str:
        """Enabled | Suspended | Off"""
        status, _, body = self._request("GET", params={"versioning": ""})
        if status != 200:
            raise self._error(status, body, "versioning 확인")
        root = _xml(body, "versioning 확인")
        for el in root.iter():
            el.tag = el.tag.rsplit("}", 1)[-1]
        return root.findtext("Status") or "Off"


def s3_endpoint(cfg: dict):
    region = cfg.get("region") or "us-east-1"
    endpoint = cfg.get("endpoint") or f"https://s3.{region}.amazonaws.com"
    u = urllib.parse.urlsplit(endpoint)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise BackendError(f"잘못된 endpoint: {endpoint!r}")
    return u


def location(cfg: dict) -> str:
    """설정이 가리키는 저장소 자리 (describe() 의 값). 같은 자리를 다르게 적어도 — 끝의 '/', host 대소문자,
    기본 포트, 기본 endpoint 를 적었는지 — 같게 나온다. init 이 이 PC 가 쓰던 저장소인지 볼 때도 쓴다."""
    kind = cfg.get("type")
    if kind == "local":
        if not cfg.get("path"):
            raise BackendError("local backend 에 path 가 없다")
        return f"local:{os.path.abspath(Path(cfg['path']).expanduser())}"
    if kind != "s3":
        raise BackendError(f"모르는 backend type: {kind!r}")
    u = s3_endpoint(cfg)
    try:
        port = u.port
    except ValueError as e:
        raise BackendError(f"잘못된 endpoint: {e}") from None
    host = u.hostname or ""
    host = f"[{host}]" if ":" in host else host
    if port and port != {"http": 80, "https": 443}[u.scheme]:
        host += f":{port}"
    prefix = (cfg.get("prefix") or "").strip("/")
    return f"s3:{u.scheme}://{host}{u.path.rstrip('/')}/{cfg.get('bucket')}/{prefix + '/' if prefix else ''}"


def _xml(body: bytes, what: str):
    try:
        return ET.fromstring(body)
    except ET.ParseError as e:
        raise BackendError(f"{what}: 응답을 읽지 못했다 ({e})") from None


CRED_KEYS = ("access_key_id", "secret_access_key", "session_token")


def env_credentials() -> dict:
    """HBRNESS_S3_* 환경변수. key id 와 secret 이 둘 다 있을 때만 한 묶음으로 쓴다 — 파일 값과 섞지 않는다."""
    env = {k: os.environ.get(f"HBRNESS_S3_{k.upper()}", "") for k in CRED_KEYS}
    if not (env["access_key_id"] and env["secret_access_key"]):
        return {}
    return {k: v for k, v in env.items() if v}


CRED_STORES = ("keychain", "secret-tool", "file")
CRED_SERVICE = "hbrness-sfstate"


def auto_credentials_store() -> str:
    """macOS 는 Keychain, Secret Service 가 있는 Linux 는 secret-tool, 아니면 파일.
    HBRNESS_CREDENTIALS_STORE 로 정해 둘 수 있다 (테스트는 file 로 둔다)."""
    forced = os.environ.get("HBRNESS_CREDENTIALS_STORE", "")
    if forced in CRED_STORES:
        return forced
    if sys.platform == "darwin" and which("security"):
        return "keychain"
    if which("secret-tool") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return "secret-tool"
    return "file"


def _cred_account(path: Path) -> str:
    """HBRNESS_HOME 마다 따로 — credentials.json 이 있을 자리(path)의 디렉토리로 정한다. 공백 없는 이름."""
    return "home-" + hashlib.sha256(str(path.parent.expanduser().resolve()).encode()).hexdigest()[:16]


def _run_secret(args, data: bytes = b"") -> subprocess.CompletedProcess:
    exe = which(args[0])
    if not exe:
        raise BackendError(f"{args[0]} 가 없다 — init --credentials-store file 로 바꿀 수 있다")
    try:
        return subprocess.run([exe, *args[1:]], input=data, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise BackendError(f"{args[0]} 를 돌리지 못했다: {e}") from None


def _keychain() -> list:
    """HBRNESS_KEYCHAIN: 기본 keychain 대신 쓸 keychain 파일 (테스트용). security 는 없는 파일을 주면 말없이 기본
    keychain 에 쓰므로, 정해 놓고 파일이 없으면 멈춘다."""
    kc = os.environ.get("HBRNESS_KEYCHAIN")
    if kc and re.search(r"[\s\"'\\]", kc):  # security -i 의 명령줄 파서를 그대로 지나가지 못한다
        raise BackendError(f"HBRNESS_KEYCHAIN 경로에 공백·따옴표·역슬래시가 있으면 쓸 수 없다: {kc!r}")
    if kc and not Path(kc).is_file():
        raise BackendError(f"HBRNESS_KEYCHAIN 의 keychain 파일이 없다: {kc}")
    return [kc] if kc else []


def _stored_credentials(store: str, path: Path) -> dict:
    acct = _cred_account(path)
    if store == "keychain":
        p = _run_secret(["security", "find-generic-password", "-a", acct, "-s", CRED_SERVICE, "-w", *_keychain()])
        if p.returncode == 44:  # 없다
            return {}
    else:
        p = _run_secret(["secret-tool", "lookup", "service", CRED_SERVICE, "account", acct])
        if p.returncode != 0 and not p.stdout.strip() and not p.stderr.strip():
            return {}
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        raise BackendError(f"{store} 에서 자격증명을 읽지 못했다 ({err[-1] if err else f'exit {p.returncode}'}) — "
                           "잠겨 있으면 풀고, 아니면 init --credentials-store file 로 바꾼다")
    try:
        data = json.loads(base64.b64decode(p.stdout.strip(), validate=True))
    except (ValueError, TypeError) as e:
        raise BackendError(f"{store} 의 자격증명을 읽지 못했다: {e}") from None
    return {k: str(v) for k, v in data.items() if k in CRED_KEYS and v} if isinstance(data, dict) else {}


def save_credentials(store: str, path: Path, creds: dict):
    """자격증명을 store 에 둔다. path 는 credentials.json 자리 (file 이면 그 파일, 아니면 계정 이름을 정한다).
    Keychain·secret-tool 에 두면 남아 있던 credentials.json 은 지운다 — 디스크에 평문으로 남기지 않게."""
    if store == "file":
        save_config(path, creds)
        return
    blob = base64.b64encode(json.dumps(creds).encode())
    acct = _cred_account(path)
    if store == "keychain":
        # security 는 argv 가 다른 사용자에게 보인다 — 명령을 stdin(-i)으로, 값은 hex(-X)로 넘긴다.
        # -i 는 실패해도 exit 0 이라 다시 읽어 맞는지 본다.
        line = " ".join(["add-generic-password", "-U", "-a", acct, "-s", CRED_SERVICE, "-X", blob.hex(), *_keychain()])
        _run_secret(["security", "-i"], (line + "\n").encode())
    elif store == "secret-tool":
        p = _run_secret(["secret-tool", "store", "--label=hbrness sfstate", "service", CRED_SERVICE, "account", acct], blob)
        if p.returncode != 0:
            raise BackendError(f"secret-tool 에 저장하지 못했다: {p.stderr.decode('utf-8', 'replace').strip()}")
    else:
        raise BackendError(f"모르는 자격증명 저장소: {store!r}")
    if _stored_credentials(store, path) != {k: v for k, v in creds.items() if v}:
        raise BackendError(f"{store} 에 자격증명을 저장하지 못했다 (잠겨 있거나 접근이 막혔다) — "
                           "init --credentials-store file 로 바꿀 수 있다")
    path.unlink(missing_ok=True)


def forget_credentials(store: str, path: Path):
    """store 에 둔 자격증명을 지운다 (둘 곳을 바꾼 뒤 예전 자리를 치울 때). 없으면 그만이다."""
    acct = _cred_account(path)
    if store == "file":
        path.unlink(missing_ok=True)
        return
    if store == "keychain":
        p = _run_secret(["security", "delete-generic-password", "-a", acct, "-s", CRED_SERVICE, *_keychain()])
        ok = p.returncode in (0, 44)  # 44: 없다
    else:
        p = _run_secret(["secret-tool", "clear", "service", CRED_SERVICE, "account", acct])
        ok = p.returncode == 0
    if not ok:
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        raise BackendError(f"{store} 의 자격증명(서비스 {CRED_SERVICE}, 계정 {acct})을 지우지 못했다 "
                           f"({err[-1] if err else f'exit {p.returncode}'})")


def load_credentials(path: Path | None, store: str = "file") -> dict:
    """환경변수 묶음이 있으면 그것을, 없으면 store 에 둔 자격증명을 쓴다. path 가 None 이면 저장된 것은 보지 않는다."""
    return env_credentials() or (stored_credentials(path, store) if path is not None else {})


def stored_credentials(path: Path, store: str = "file") -> dict:
    """store 에 둔 자격증명 (환경변수는 보지 않는다). 없으면 {}."""
    if store != "file":
        return _stored_credentials(store, path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BackendError(f"{path} 를 읽지 못했다: {e}")
    if not isinstance(data, dict):
        raise BackendError(f"{path} 가 JSON 객체가 아니다")
    return {k: str(v) for k, v in data.items() if k in CRED_KEYS and v}


def make_backend(cfg: dict, creds_path: Path | None = None, key_path: Path | None = None):
    kind = cfg.get("type")
    if kind == "local":
        if not cfg.get("path"):
            raise BackendError("local backend 에 path 가 없다")
        be = LocalBackend(cfg["path"])
    elif kind == "s3":
        be = S3Backend(cfg, load_credentials(creds_path, cfg.get("credentials") or "file"))
    else:
        raise BackendError(f"모르는 backend type: {kind!r}")
    be.encryption = cfg.get("encryption") or None
    be.key_path = key_path
    return be


def load_config(path: Path):
    """설정 파일이 없으면 None. 있는데 읽을 수 없으면 BackendError."""
    if not path.exists():
        return None
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BackendError(f"{path} 를 읽지 못했다: {e}")
    if not isinstance(cfg, dict):
        raise BackendError(f"{path} 가 JSON 객체가 아니다")
    return cfg


def credentials_file(config_path: Path) -> Path:
    return config_path.with_name("credentials.json")


def key_file(config_path: Path) -> Path:
    return config_path.with_name("age.key")


def load_backend(path: Path):
    cfg = load_config(path)
    return make_backend(cfg, credentials_file(path), key_file(path)) if cfg is not None else None


def save_config(path: Path, cfg: dict):
    """mode 600 으로 쓴다. 자격증명이 잠깐이라도 다른 사용자에게 읽히지 않게 임시 파일부터 600 으로 만든다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with contextlib.suppress(FileNotFoundError):
        tmp.unlink()  # 앞서 끊긴 쓰기의 잔재
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


# ─────────────────────────────────────────────────────────────────────────────
# 로컬 캐시
# ─────────────────────────────────────────────────────────────────────────────

def _prune_empty(d: Path, stop: Path):
    """d 부터 stop 직전까지 빈 디렉토리를 지운다."""
    stop = stop.resolve()
    d = d.resolve()
    while d != stop and stop in d.parents:
        try:
            d.rmdir()
        except OSError:
            return
        d = d.parent


def _read(path: Path):
    try:
        return path.read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def tombstone() -> bytes:
    info = {"deleted": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "host": socket.gethostname().split(".")[0]}
    return TOMBSTONE + json.dumps(info).encode() + b"\n"


def is_tombstone(data: bytes) -> bool:
    return data.startswith(TOMBSTONE)


def live(ent) -> bool:
    """manifest 항목이 살아 있는 파일인가 (tombstone 을 맞춘 항목은 {"etag", "deleted": true})."""
    return bool(ent) and not ent.get("deleted")


def _syncable(rel: str) -> bool:
    parts = rel.split("/")
    return (len(parts) >= 2 and not parts[0].startswith(("_", "."))
            and parts[-1] not in SKIP_FILES and not parts[-1].startswith("."))


class Cache:
    def __init__(self, root: Path, backend):
        self.root = Path(root)
        self.backend = backend
        self.manifest_file = self.root / META_DIR / "manifest.json"
        self.store = backend.identity()
        self.entries = self._load()

    def _load(self) -> dict:
        try:
            m = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        # backend 를 바꿨거나 저장소를 새로 만들었으면 예전 etag 는 의미가 없다 — 처음부터 다시 맞춘다.
        # 그래야 빈 새 저장소를 '원격에서 다 지웠다' 로 읽지 않는다.
        if not isinstance(m, dict) or m.get("store") != self.store:
            return {}
        e = m.get("entries")
        return e if isinstance(e, dict) else {}

    def save(self):
        self.manifest_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_file.with_name("manifest.json.tmp")
        tmp.write_text(json.dumps({"version": 2, "store": self.store, "entries": self.entries},
                                  ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.manifest_file)

    def synced(self, rel: str) -> bool:
        """로컬 파일이 마지막으로 맞춘 원격 버전과 같은가."""
        ent = self.entries.get(rel)
        data = _read(self.root / rel)
        return live(ent) and data is not None and sha256(data) == ent["sha256"]

    def local_files(self, rel_prefix: str = "") -> dict:
        """동기화 대상 로컬 파일. 읽지 못한 디렉토리가 있으면 OSError — 빠진 파일을 삭제로 읽으면 안 된다."""
        base = self.root / rel_prefix if rel_prefix else self.root
        out = {}
        if not os.path.lexists(base):
            return out  # 프로젝트 디렉토리째 지웠다 (clear 스킬) — 전부 삭제가 맞다

        def fail(err):
            raise err

        if not base.is_dir():
            raise NotADirectoryError(str(base))
        for dirpath, dirnames, filenames in os.walk(base, onerror=fail):
            dirnames[:] = [n for n in dirnames if not n.startswith(".")]
            rel_dir = Path(dirpath).relative_to(self.root).as_posix()
            for fn in filenames:
                rel = fn if rel_dir == "." else f"{rel_dir}/{fn}"
                if _syncable(rel):
                    out[rel] = Path(dirpath) / fn
        return out

    def _write(self, rel: str, data: bytes):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".tmp-{os.getpid()}-{p.name}")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def _remove(self, rel: str):
        p = self.root / rel
        p.unlink(missing_ok=True)
        _prune_empty(p.parent, self.root)

    def _set_aside(self, rel: str) -> Path:
        """이 PC 의 버전을 _conflicts/ 로 옮긴다."""
        src = self.root / rel
        stem, dot, ext = rel.rpartition(".")
        if not dot or "/" in ext:
            stem, ext = rel, ""
        host = socket.gethostname().split(".")[0] or "host"
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = f".{ext}" if ext else ""
        base = self.root / CONFLICT_DIR / f"{stem}.{host}-{stamp}"
        base.parent.mkdir(parents=True, exist_ok=True)
        n = 1
        while True:
            dst = base.with_name(base.name + (f"-{n}" if n > 1 else "") + suffix)
            try:
                os.link(src, dst)  # 이미 있으면 실패한다 — 앞선 충돌 사본을 덮어쓰지 않는다
            except FileExistsError:
                n += 1
                continue
            src.unlink()
            return dst

    def _accept(self, rel: str, data: bytes, etag: str, local, rep: dict, set_aside=False):
        """원격본을 원래 자리에 둔다. set_aside 면 이 PC 의 버전을 먼저 _conflicts/ 로 옮긴다."""
        if set_aside:
            rep["conflicts"].append((rel, self._set_aside(rel)))
        if set_aside or local != data:
            self._write(rel, data)
        self.entries[rel] = {"etag": etag, "sha256": sha256(data)}

    def pull(self) -> dict:
        rep = {"got": [], "removed": [], "conflicts": []}
        try:
            self._pull(rep)
        except PartialSync:
            raise
        except (BackendError, OSError) as e:
            raise PartialSync(str(e), rep) from e
        return rep

    def _pull(self, rep: dict):
        remote = {}
        for key, etag in self.backend.list(REMOTE_PREFIX).items():
            rel = key[len(REMOTE_PREFIX):]
            if _syncable(rel):
                check_key(rel)
                remote[rel] = etag
        try:
            for rel, etag in sorted(remote.items()):
                ent = self.entries.get(rel)
                if ent and ent["etag"] == etag:
                    continue
                r = self.backend.get(REMOTE_PREFIX + rel)
                if r is None:  # 목록을 받은 뒤에 지워졌다
                    continue
                data, etag = r
                local = _read(self.root / rel)
                if is_tombstone(data):  # 다른 PC 가 지웠다
                    self._gone(rel, ent, local, rep)
                    self.entries[rel] = {"etag": etag, "deleted": True}
                    continue
                # 이 PC 에서도 바뀌었나: manifest 에 없는데 파일이 있거나, 맞춘 뒤로 내용이 달라졌다
                changed_here = local is not None and (not live(ent) or sha256(local) != ent["sha256"])
                if changed_here and local != data:
                    self._accept(rel, data, etag, local, rep, set_aside=True)
                else:
                    if local != data:
                        rep["got"].append(rel)
                    self._accept(rel, data, etag, local, rep)
            for rel in [r for r in self.entries if r not in remote]:  # object 째 없어졌다 (1.5 까지의 삭제 등)
                self._gone(rel, self.entries.pop(rel), _read(self.root / rel), rep)
        finally:
            self.save()

    def _gone(self, rel: str, ent, local, rep: dict):
        """원격에서 지워졌다. 맞춘 그대로인 로컬 사본만 지운다. 이 PC 에서 고친 파일은 남긴다 — 다음 push 가
        다시 올린다 (tombstone 이면 그 etag 로, object 째 없으면 새 파일로)."""
        if local is not None and live(ent) and sha256(local) == ent["sha256"]:
            self._remove(rel)
            rep["removed"].append(rel)

    def push(self, rel_prefix: str = "") -> dict:
        rep = {"put": [], "deleted": [], "got": [], "conflicts": []}
        try:
            self._push(rel_prefix, rep)
        except PartialSync:
            raise
        except (BackendError, OSError) as e:
            raise PartialSync(str(e), rep) from e
        return rep

    def _push(self, rel_prefix: str, rep: dict):
        pre = rel_prefix.strip("/") + "/" if rel_prefix else ""
        files = self.local_files(rel_prefix)
        try:
            for rel, path in sorted(files.items()):
                data = path.read_bytes()
                h = sha256(data)
                ent = self.entries.get(rel)
                if live(ent) and ent["sha256"] == h:
                    continue
                key = REMOTE_PREFIX + rel
                try:
                    if ent:  # 살아 있는 버전이든 tombstone 이든 맞춘 그 etag 에서 바꾼다
                        etag = self.backend.put(key, data, if_match=ent["etag"])
                    else:
                        etag = self.backend.put(key, data, if_none_match=True)
                except PreconditionFailed:
                    r = self.backend.get(key)
                    if r is None:  # object 째 없어졌다 — 이 PC 의 내용을 새 파일로 올린다
                        etag = self.backend.put(key, data, if_none_match=True)
                    elif is_tombstone(r[0]):  # 다른 PC 가 지웠다 — 이 PC 에서 고친(만든) 내용을 다시 올린다
                        etag = self.backend.put(key, data, if_match=r[1])
                    else:
                        self._accept(rel, r[0], r[1], data, rep, set_aside=r[0] != data)
                        continue
                self.entries[rel] = {"etag": etag, "sha256": h}
                rep["put"].append(rel)
            for rel in sorted(r for r in self.entries if r.startswith(pre) and r not in files and live(self.entries[r])):
                key = REMOTE_PREFIX + rel
                try:
                    etag = self.backend.put(key, tombstone(), if_match=self.entries[rel]["etag"])
                except PreconditionFailed:
                    r = self.backend.get(key)
                    if r is None:  # 이미 object 째 없다
                        del self.entries[rel]
                    elif is_tombstone(r[0]):  # 다른 PC 가 먼저 지웠다
                        self.entries[rel] = {"etag": r[1], "deleted": True}
                    else:  # 지우기 전에 다른 PC 가 고쳤다 — 지우지 않고 그 버전을 받는다
                        self._accept(rel, r[0], r[1], None, rep)
                        rep["got"].append(rel)
                    continue
                self.entries[rel] = {"etag": etag, "deleted": True}
                rep["deleted"].append(rel)
        finally:
            self.save()
