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

동기화하지 않는 것: 최상위의 '_'·'.' 로 시작하는 디렉토리(_local, _conflicts, .sfstate, .git),
최상위 파일(README.md 등), INDEX.md(각 PC 가 다시 만드는 생성물), '.' 로 시작하는 파일.

설정 파일(backend.json):
  {"type": "local", "path": "/some/dir"}   디렉토리 하나를 원격처럼 쓴다 (테스트·오프라인용)
  {"type": "s3", "endpoint": "https://…", "bucket": "b", "prefix": "hbrness/", "region": "auto",
   "path_style": true}                     S3 API 를 쓰는 저장소 (AWS S3·R2·MinIO 등). SigV4 서명을 직접 한다.

s3 자격증명은 backend.json 옆의 credentials.json(mode 600)에 둔다:
  {"access_key_id": "…", "secret_access_key": "…", "session_token": "…(선택)"}
환경변수 HBRNESS_S3_ACCESS_KEY_ID 와 HBRNESS_S3_SECRET_ACCESS_KEY 가 둘 다 있으면 (HBRNESS_S3_SESSION_TOKEN 과 함께)
한 묶음으로 그쪽을 먼저 쓴다. 파일 값과 섞지 않는다.

저장소마다 표시 object(<prefix>.sfbackend, local 은 <dir>/.sfbackend)에 저장소 ID 를 적어 둔다.
표시가 없으면 원격에 닿지 못한 것으로 보고 실패한다. manifest 는 이 ID 에 묶인다.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import hmac
import http.client
import socket
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


# ─────────────────────────────────────────────────────────────────────────────
# backend
# ─────────────────────────────────────────────────────────────────────────────

class LocalBackend:
    """디렉토리 하나를 원격처럼 쓴다. etag 는 내용의 sha256 이다.
    conditional write 는 디렉토리의 .lock 을 flock 으로 잡고 확인과 쓰기를 한 번에 한다.
    init 이 표시 파일(.sfbackend)을 만들고 저장소 ID 를 적는다. 표시 파일이 없으면 디렉토리가 옮겨졌거나
    빠진 것으로 보고 실패한다 — 빈 목록으로 읽으면 pull 이 로컬 사본을 전부 지운다. 같은 경로에 저장소를
    새로 만들면 ID 가 달라져서 예전 manifest 를 버린다 (identity)."""

    MARKER = ".sfbackend"

    def __init__(self, path):
        self.root = Path(path).expanduser()

    def describe(self) -> str:
        return f"local:{os.path.abspath(self.root)}"

    def ensure(self):
        """init 에서만 부른다. 원격 디렉토리를 만들고, 표시 파일이 없으면 새 저장소 ID 로 만든다."""
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root / self.MARKER
        if not marker.is_file() or not marker.read_text(encoding="utf-8").strip():
            marker.write_text(uuid.uuid4().hex + "\n", encoding="utf-8")

    def _check(self):
        if not (self.root / self.MARKER).is_file():
            raise BackendError(f"원격 디렉토리 {self.root} 에 닿을 수 없다 (옮겼거나 빠졌으면 init 을 다시 한다)")

    def identity(self) -> str:
        """manifest 가 가리키는 저장소. 경로가 같아도 저장소를 새로 만들었으면 달라진다."""
        self._check()
        return f"{self.describe()}#{(self.root / self.MARKER).read_text(encoding='utf-8').strip()}"

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

    def get(self, key: str):
        self._check()
        try:
            data = self._path(key).read_bytes()
        except FileNotFoundError:
            return None
        return data, sha256(data)

    def stat(self, key: str):
        r = self.get(key)
        return r[1] if r else None

    def put(self, key: str, data: bytes, if_match: str | None = None, if_none_match: bool = False) -> str:
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


class S3Backend:
    """S3 API 저장소. ETag 를 etag 로 쓰고, PutObject 의 If-Match / If-None-Match 로 conditional write 를 한다.
    DeleteObject 는 If-Match 를 보내되, 지원하지 않는 저장소도 있어 HEAD 로 먼저 etag 를 확인한다."""

    MARKER = ".sfbackend"
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
        endpoint = cfg.get("endpoint") or f"https://s3.{self.region}.amazonaws.com"
        u = urllib.parse.urlsplit(endpoint)
        if u.scheme not in ("http", "https") or not u.netloc:
            raise BackendError(f"잘못된 endpoint: {endpoint!r}")
        self.scheme = u.scheme
        self.base_path = u.path.rstrip("/")
        self.path_style = bool(cfg.get("path_style", bool(cfg.get("endpoint"))))
        self.host = u.netloc if self.path_style else f"{self.bucket}.{u.netloc}"
        self.endpoint = f"{u.scheme}://{u.netloc}{self.base_path}"
        self.creds = creds

    def describe(self) -> str:
        return f"s3:{self.endpoint}/{self.bucket}/{self.prefix}"

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

    def ensure(self):
        """init 에서만 부른다. bucket 에 닿는지 보고, 표시 object 가 없으면 새 저장소 ID 로 만든다."""
        self.list("", limit=1)
        try:
            self._put_raw(self.prefix + self.MARKER, (uuid.uuid4().hex + "\n").encode(), if_none_match=True)
        except PreconditionFailed:
            pass

    def identity(self) -> str:
        r = self._get_raw(self.prefix + self.MARKER)
        if r is None:
            raise BackendError(f"{self.describe()} 에 저장소 표시({self.MARKER})가 없다 — 지웠거나 다른 곳이면 init 을 다시 한다")
        return f"{self.describe()}#{r[0].decode('utf-8', 'replace').strip()}"

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

    def _get_raw(self, full_key: str):
        status, headers, body = self._request("GET", full_key)
        if status == 404:
            return None
        if status != 200:
            raise self._error(status, body, f"읽기 {full_key}")
        return body, self._etag(headers)

    def get(self, key: str):
        check_key(key)
        return self._get_raw(self.prefix + key)

    def stat(self, key: str):
        check_key(key)
        status, headers, body = self._request("HEAD", self.prefix + key)
        if status == 404:
            return None
        if status != 200:
            raise self._error(status, body, f"확인 {key}")
        return self._etag(headers)

    def _put_raw(self, full_key: str, data: bytes, if_match=None, if_none_match=False) -> str:
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

    def put(self, key: str, data: bytes, if_match: str | None = None, if_none_match: bool = False) -> str:
        check_key(key)
        return self._put_raw(self.prefix + key, data, if_match=if_match, if_none_match=if_none_match)

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

    def versioning(self) -> str:
        """Enabled | Suspended | Off"""
        status, _, body = self._request("GET", params={"versioning": ""})
        if status != 200:
            raise self._error(status, body, "versioning 확인")
        root = ET.fromstring(body)
        for el in root.iter():
            el.tag = el.tag.rsplit("}", 1)[-1]
        return root.findtext("Status") or "Off"


CRED_KEYS = ("access_key_id", "secret_access_key", "session_token")


def env_credentials() -> dict:
    """HBRNESS_S3_* 환경변수. key id 와 secret 이 둘 다 있을 때만 한 묶음으로 쓴다 — 파일 값과 섞지 않는다."""
    env = {k: os.environ.get(f"HBRNESS_S3_{k.upper()}", "") for k in CRED_KEYS}
    if not (env["access_key_id"] and env["secret_access_key"]):
        return {}
    return {k: v for k, v in env.items() if v}


def load_credentials(path: Path | None) -> dict:
    """환경변수 묶음이 있으면 그것을, 없으면 credentials.json 을 쓴다. path 가 None 이면 파일은 보지 않는다."""
    env = env_credentials()
    if env:
        return env
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BackendError(f"{path} 를 읽지 못했다: {e}")
    if not isinstance(data, dict):
        raise BackendError(f"{path} 가 JSON 객체가 아니다")
    return {k: str(v) for k, v in data.items() if k in CRED_KEYS and v}


def make_backend(cfg: dict, creds_path: Path | None = None):
    kind = cfg.get("type")
    if kind == "local":
        if not cfg.get("path"):
            raise BackendError("local backend 에 path 가 없다")
        return LocalBackend(cfg["path"])
    if kind == "s3":
        return S3Backend(cfg, load_credentials(creds_path))
    raise BackendError(f"모르는 backend type: {kind!r}")


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


def load_backend(path: Path):
    cfg = load_config(path)
    return make_backend(cfg, credentials_file(path)) if cfg is not None else None


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
        tmp.write_text(json.dumps({"version": 1, "store": self.store, "entries": self.entries},
                                  ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.manifest_file)

    def synced(self, rel: str) -> bool:
        """로컬 파일이 마지막으로 맞춘 원격 버전과 같은가."""
        ent = self.entries.get(rel)
        data = _read(self.root / rel)
        return bool(ent) and data is not None and sha256(data) == ent["sha256"]

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
                # 이 PC 에서도 바뀌었나: manifest 에 없는데 파일이 있거나, 맞춘 뒤로 내용이 달라졌다
                changed_here = local is not None and (not ent or sha256(local) != ent["sha256"])
                if changed_here and local != data:
                    self._accept(rel, data, etag, local, rep, set_aside=True)
                else:
                    if local != data:
                        rep["got"].append(rel)
                    self._accept(rel, data, etag, local, rep)
            for rel in [r for r in self.entries if r not in remote]:
                ent = self.entries.pop(rel)
                local = _read(self.root / rel)
                if local is not None and sha256(local) == ent["sha256"]:
                    self._remove(rel)
                    rep["removed"].append(rel)
                # 로컬에서 고친 파일은 남긴다 — manifest 에서 빠졌으니 다음 push 가 새 파일로 올린다
        finally:
            self.save()

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
                if ent and ent["sha256"] == h:
                    continue
                key = REMOTE_PREFIX + rel
                try:
                    if ent:
                        etag = self.backend.put(key, data, if_match=ent["etag"])
                    else:
                        etag = self.backend.put(key, data, if_none_match=True)
                except PreconditionFailed:
                    r = self.backend.get(key)
                    if r is None:  # 다른 PC 가 지웠다 — 이 PC 에서 고친 내용을 새 파일로 올린다
                        etag = self.backend.put(key, data, if_none_match=True)
                    else:
                        self._accept(rel, r[0], r[1], data, rep, set_aside=r[0] != data)
                        continue
                self.entries[rel] = {"etag": etag, "sha256": h}
                rep["put"].append(rel)
            for rel in sorted(r for r in self.entries if r.startswith(pre) and r not in files):
                key = REMOTE_PREFIX + rel
                try:
                    if self.backend.delete(key, if_match=self.entries[rel]["etag"]):
                        rep["deleted"].append(rel)
                except PreconditionFailed:
                    # 지우기 전에 다른 PC 가 고쳤다 — 지우지 않고 그 버전을 받는다
                    r = self.backend.get(key)
                    if r is not None:
                        self._accept(rel, r[0], r[1], None, rep)
                        rep["got"].append(rel)
                        continue
                del self.entries[rel]
        finally:
            self.save()
