"""KB filesystem layer — atomic writes, slug normalization, INDEX maintenance.

Storage location follows hbrness Tier 1 convention:
    ~/.hbrness/llm-kb/
        entries/{slug}.md
        INDEX.md
        links.json
        config.yaml
        worker.log              # rotated by worker, sized for debugging
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import tempfile
from pathlib import Path

KB_ROOT = Path.home() / ".hbrness" / "llm-kb"
ENTRIES_DIR = KB_ROOT / "entries"
INDEX_PATH = KB_ROOT / "INDEX.md"
LINKS_PATH = KB_ROOT / "links.json"
CONFIG_PATH = KB_ROOT / "config.yaml"
WORKER_LOG = KB_ROOT / "worker.log"


def ensure_dirs() -> None:
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)


def slugify(name: str) -> str:
    """Lowercase kebab slug, ASCII-fallback for Korean/non-Latin letters.

    For Korean concept names that have an English/Latin alias, the judge LLM
    is instructed to choose an English-or-romanized slug. As a safety net we
    still produce *some* slug from anything thrown at us.
    """
    s = name.strip().lower()
    # Replace non-alphanumeric runs with single dash, keep digits + hyphens.
    s = re.sub(r"[^\w\-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "entry-" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return s[:80]


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def entry_path(slug: str) -> Path:
    return ENTRIES_DIR / f"{slug}.md"


def entry_exists(slug: str) -> bool:
    return entry_path(slug).is_file()


def read_entry(slug: str) -> str | None:
    p = entry_path(slug)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def write_entry(slug: str, content: str) -> Path:
    """Atomically write an entry markdown file."""
    ensure_dirs()
    path = entry_path(slug)
    _atomic_write(path, content)
    return path


def list_entries() -> list[dict]:
    """List all entries as ``[{slug, name, description, domain, updated_at}]``."""
    ensure_dirs()
    out: list[dict] = []
    for p in sorted(ENTRIES_DIR.glob("*.md")):
        slug = p.stem
        meta = _read_frontmatter(p)
        out.append({
            "slug": slug,
            "name": meta.get("name", slug),
            "description": meta.get("description", ""),
            "domain": meta.get("domain", []),
            "updated_at": meta.get("updated_at", ""),
        })
    return out


def _read_frontmatter(path: Path) -> dict:
    """Tiny YAML-frontmatter reader for the subset we write ourselves."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = text[4:end]
    out: dict = {}
    current_list_key = None
    for line in fm.split("\n"):
        if not line.strip():
            current_list_key = None
            continue
        # YAML list continuation
        if line.startswith("  - ") and current_list_key:
            out.setdefault(current_list_key, []).append(line[4:].strip().strip('"').strip("'"))
            continue
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if v == "":
                current_list_key = k
                out[k] = []
            elif v.startswith("[") and v.endswith("]"):
                inner = v[1:-1]
                out[k] = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
                current_list_key = None
            else:
                out[k] = v.strip('"').strip("'")
                current_list_key = None
    return out


def update_index() -> None:
    """Regenerate INDEX.md from entries/ contents. Cheap full rebuild."""
    entries = list_entries()
    by_domain: dict[str, list[dict]] = {}
    for e in entries:
        domains = e.get("domain") or ["misc"]
        if isinstance(domains, str):
            domains = [domains]
        for d in domains:
            by_domain.setdefault(d, []).append(e)

    now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).isoformat(timespec="seconds")
    lines = [
        "# Knowledge Base Index",
        "",
        f"> 마지막 갱신: {now}  ·  총 {len(entries)}개 항목",
        "",
    ]
    for domain in sorted(by_domain.keys()):
        lines.append(f"## {domain}")
        for e in sorted(by_domain[domain], key=lambda x: x["slug"]):
            desc = e.get("description") or ""
            short = (desc[:80] + "…") if len(desc) > 80 else desc
            lines.append(f"- [{e['name']}](entries/{e['slug']}.md) — {short}".rstrip(" —"))
        lines.append("")

    _atomic_write(INDEX_PATH, "\n".join(lines))


def append_link(from_slug: str, to_slug: str) -> None:
    """Append a directed edge (from → to) to links.json. Idempotent."""
    ensure_dirs()
    data: dict = {}
    if LINKS_PATH.is_file():
        try:
            data = json.loads(LINKS_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    edges = set(tuple(e) for e in data.get("edges", []))
    edges.add((from_slug, to_slug))
    data["edges"] = sorted(edges)
    _atomic_write(LINKS_PATH, json.dumps(data, ensure_ascii=False, indent=2))


def log(msg: str) -> None:
    """Append a single timestamped line to the worker log. Best-effort."""
    try:
        ensure_dirs()
        ts = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).isoformat(timespec="seconds")
        with open(WORKER_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
        # Cheap rotation: cap at ~200KB
        if WORKER_LOG.stat().st_size > 200_000:
            rotated = WORKER_LOG.with_suffix(".log.1")
            os.replace(WORKER_LOG, rotated)
    except OSError:
        pass


def is_disabled() -> bool:
    """Honor a simple kill switch — `~/.hbrness/llm-kb/config.yaml` with `enabled: false`."""
    if not CONFIG_PATH.is_file():
        return False
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("enabled:"):
            v = line.split(":", 1)[1].strip().strip('"').strip("'").lower()
            return v in ("false", "no", "0", "off")
    return False
