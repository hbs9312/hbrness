#!/usr/bin/env python3
"""ghflow SessionStart hook — fetch issue & PR templates for the current repo.

Runs on every Claude Code session start. Fetches templates from both:
  - The current repository (takes precedence)
  - The organization's `.github` repository

Writes the combined result to `/tmp/ghflow/<org>__<repo>/templates.json`
so the ghflow skills (create-issue, create-pr) can consume them without
any caching logic of their own. The file is overwritten every session
start, so there is no stale data.

Silent no-op when:
  - The `gh` CLI is missing or unauthenticated
  - The current working directory is not inside a GitHub repository
  - Network calls fail (partial data is still written when possible)
"""

from __future__ import annotations

import base64
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

GH_TIMEOUT = 5  # seconds per gh call

PR_TEMPLATE_PATHS = [
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/pull_request_template.md",
    "docs/pull_request_template.md",
    "PULL_REQUEST_TEMPLATE.md",
    "pull_request_template.md",
]

PR_TEMPLATE_DIRS = [
    ".github/PULL_REQUEST_TEMPLATE",
    ".github/pull_request_template",
    "docs/PULL_REQUEST_TEMPLATE",
    "docs/pull_request_template",
    "PULL_REQUEST_TEMPLATE",
    "pull_request_template",
]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=GH_TIMEOUT)
        return r.returncode, r.stdout
    except Exception:
        return 1, ""


def gh_json(*args: str):
    code, out = _run(["gh", *args])
    if code != 0 or not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def gh_api_content(path: str) -> str | None:
    code, out = _run(["gh", "api", path, "-q", ".content"])
    if code != 0 or not out.strip():
        return None
    try:
        return base64.b64decode(out.strip()).decode("utf-8")
    except Exception:
        return None


def gh_api_list(path: str) -> list:
    data = gh_json("api", path)
    return data if isinstance(data, list) else []


def _parse_list_value(raw: str) -> list[str]:
    s = raw.strip()
    if s.startswith("["):
        s = s.strip("[]")
    return [p.strip().strip("\"'") for p in s.split(",") if p.strip()]


def parse_issue_template(filename: str, content: str, source: str) -> dict:
    """Parse a markdown issue template with optional YAML-ish frontmatter.

    This is intentionally lenient — GitHub's YAML frontmatter is simple
    (flat key: value pairs) so we avoid pulling in PyYAML.
    """
    tpl = {
        "source": source,
        "filename": filename,
        "name": filename,
        "title_prefix": "",
        "labels": [],
        "assignees": [],
        "body": content,
    }
    m = FRONTMATTER_RE.match(content)
    if not m:
        return tpl
    fm_raw, body = m.group(1), m.group(2)
    tpl["body"] = body
    for line in fm_raw.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip().strip("\"'")
        if key == "name":
            tpl["name"] = val
        elif key == "title":
            tpl["title_prefix"] = val
        elif key in ("labels", "assignees"):
            tpl[key] = _parse_list_value(val)
    return tpl


def fetch_issue_templates(org: str, repo: str) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    sources = [
        (f"{org}/{repo}", f"{org}/{repo}"),
        (f"{org}/.github", f"{org}/.github"),
    ]
    for owner_repo, tag in sources:
        items = gh_api_list(f"repos/{owner_repo}/contents/.github/ISSUE_TEMPLATE")
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "file":
                continue
            name = item.get("name", "")
            if not name.endswith((".md", ".yml", ".yaml")):
                continue
            if name in seen:
                continue  # current repo wins
            seen.add(name)
            content = gh_api_content(
                f"repos/{owner_repo}/contents/.github/ISSUE_TEMPLATE/{name}"
            )
            if content is None:
                continue
            results.append(parse_issue_template(name, content, tag))
    return results


def fetch_pr_templates(org: str, repo: str) -> list[dict]:
    """Fetch PR templates from both the current repo and the org's .github repo.

    Handles both GitHub-supported layouts:
    - Single file (`.github/PULL_REQUEST_TEMPLATE.md`)
    - Multiple templates in a directory (`.github/PULL_REQUEST_TEMPLATE/*.md`)

    Source precedence: current repo is checked first; if it yields any
    templates, the org fallback is skipped so we don't mix incompatible
    template sets across sources.
    """
    sources = [
        (f"{org}/{repo}", f"{org}/{repo}"),
        (f"{org}/.github", f"{org}/.github"),
    ]
    results: list[dict] = []
    for owner_repo, tag in sources:
        found_for_source: list[dict] = []

        # Single-file form
        for p in PR_TEMPLATE_PATHS:
            content = gh_api_content(f"repos/{owner_repo}/contents/{p}")
            if content:
                found_for_source.append({"source": tag, "path": p, "body": content})
                break  # one single-file template is enough

        # Directory form (multiple templates)
        for d in PR_TEMPLATE_DIRS:
            items = gh_api_list(f"repos/{owner_repo}/contents/{d}")
            if not items:
                continue
            for item in items:
                if not isinstance(item, dict) or item.get("type") != "file":
                    continue
                name = item.get("name", "")
                if not name.endswith(".md"):
                    continue
                content = gh_api_content(f"repos/{owner_repo}/contents/{d}/{name}")
                if content:
                    found_for_source.append(
                        {"source": tag, "path": f"{d}/{name}", "body": content}
                    )
            if found_for_source:
                break  # stop at the first directory location that yields files

        if found_for_source:
            results.extend(found_for_source)
            break  # current repo wins — don't fall back to org
    return results


def main() -> int:
    if shutil.which("gh") is None:
        return 0
    info = gh_json("repo", "view", "--json", "nameWithOwner,owner")
    if not info or "nameWithOwner" not in info:
        return 0

    repo_nwo = info["nameWithOwner"]
    org = info["owner"]["login"]
    repo = repo_nwo.split("/", 1)[1]

    payload = {
        "repo": repo_nwo,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "issue_templates": fetch_issue_templates(org, repo),
        "pr_templates": fetch_pr_templates(org, repo),
    }

    slug = repo_nwo.replace("/", "__")
    out_dir = Path("/tmp/ghflow") / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "templates.json"
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # never fail session start
        print(f"ghflow session-start hook: {e}", file=sys.stderr)
        sys.exit(0)
