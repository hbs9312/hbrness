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
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import socket
import uuid
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


def make_backend(cfg: dict):
    kind = cfg.get("type")
    if kind == "local":
        if not cfg.get("path"):
            raise BackendError("local backend 에 path 가 없다")
        return LocalBackend(cfg["path"])
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


def load_backend(path: Path):
    cfg = load_config(path)
    return make_backend(cfg) if cfg is not None else None


def save_config(path: Path, cfg: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
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
