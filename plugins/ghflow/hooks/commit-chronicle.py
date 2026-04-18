#!/usr/bin/env python3
"""ghflow PostToolUse hook — nudge Claude to chronicle a successful git commit.

Runs after every Bash tool invocation. When the command is a real `git commit`
that produced a new commit in a git repository, emit an `additionalContext`
payload that reminds Claude to invoke the `ghflow:chronicle` skill so the
intent/decisions/context of the commit get captured into
`~/.commit-chronicles/` while the session context is still fresh.

Key behaviours:
  - Nudge-only. Never blocks. Claude may ignore if context is insufficient.
  - Idempotent. If a chronicle file for the commit SHA already exists, the
    hook stays silent so rebases/amends/no-ops do not trigger duplicate
    chronicle writes.
  - Pure detection. Writing the chronicle is the skill's job; the hook only
    carries the commit identity + a reminder.

Silent no-op when:
  - Tool isn't Bash.
  - Command isn't a real `git commit` (help, --dry-run, no-verify echo, etc.).
  - Command exited non-zero (commit failed).
  - `git` is missing or the working directory isn't a git repo.
  - A chronicle already exists for the new HEAD SHA.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

GIT_TIMEOUT = 5  # seconds

# Flags that mean the command is NOT producing a new commit.
NON_COMMIT_FLAGS = (
    "--help",
    "-h",
    "--dry-run",
    "--status",
    "--no-status",
    "--short",
    "--porcelain",
    "--long",
    "--branch",
    "--verbose",
)


def _read_stdin_json() -> dict:
    try:
        data = sys.stdin.read()
        if not data:
            return {}
        return json.loads(data)
    except Exception:
        return {}


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            cwd=cwd,
        )
        return r.returncode, r.stdout.strip()
    except Exception:
        return 1, ""


def _looks_like_commit(command: str) -> bool:
    """Best-effort check that `command` is a real `git commit` invocation.

    Requires `git commit` to appear as the leading verb of at least one
    shell segment (split on `;`, `&&`, `||`) so that strings like
    `echo git commit is great` or `grep 'git commit' file` do NOT match.
    Tolerates leading env-var assignments (`GIT_AUTHOR_NAME=x git commit ...`)
    and trailing subcommand arguments. Intentionally permissive on `git -C
    <path> commit` — an uncommon form; the skill validates the SHA again
    afterwards so false positives remain cheap.
    """
    if not command:
        return False
    segments = re.split(r"&&|\|\||;|\n", command)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        # Drop leading env var assignments (FOO=bar BAZ=qux git commit ...)
        seg = re.sub(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)+", "", seg)
        m = re.match(r"^git\s+commit\b(.*)$", seg)
        if not m:
            continue
        rest = m.group(1)
        for flag in NON_COMMIT_FLAGS:
            if re.search(rf"(?:^|\s){re.escape(flag)}(?:\s|$|=)", rest):
                return False
        return True
    return False


def _repo_slug_from_remote(cwd: str) -> str | None:
    code, url = _run(["git", "config", "--get", "remote.origin.url"], cwd=cwd)
    if code != 0 or not url:
        return None
    # Normalise: git@github.com:owner/repo.git  OR  https://github.com/owner/repo(.git)
    m = re.match(r"^(?:git@|ssh://git@|https?://)([^/:]+)[/:]([^/]+)/(.+?)(?:\.git)?/?$", url)
    if not m:
        return None
    host, owner, repo = m.group(1), m.group(2), m.group(3)
    return f"{host}__{owner}__{repo}"


def _repo_slug_fallback(cwd: str) -> str:
    """Deterministic slug for repos with no remote (local-only)."""
    import hashlib

    name = os.path.basename(os.path.abspath(cwd)) or "repo"
    h = hashlib.sha1(os.path.abspath(cwd).encode()).hexdigest()[:8]
    return f"local__{name}__{h}"


def _chronicle_exists(slug: str, sha: str) -> bool:
    root = Path.home() / ".commit-chronicles" / slug
    if not root.exists():
        return False
    # Chronicle filenames contain the short SHA; cheap glob.
    short = sha[:7]
    for _ in root.rglob(f"*-{short}-*.md"):
        return True
    return False


def _emit(additional_context: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": additional_context,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    event = _read_stdin_json()
    if event.get("tool_name") != "Bash":
        return 0

    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response") or {}
    command = (tool_input.get("command") or "").strip()

    # Exit code may live under a few keys depending on harness version.
    exit_code = (
        tool_response.get("exit_code")
        if tool_response.get("exit_code") is not None
        else tool_response.get("returncode", 0)
    )
    if tool_response.get("interrupted"):
        return 0
    if not isinstance(exit_code, int):
        exit_code = 0
    if exit_code != 0:
        return 0

    if not _looks_like_commit(command):
        return 0

    cwd = os.getcwd()
    code, _ = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=cwd)
    if code != 0:
        return 0

    code, head_sha = _run(["git", "rev-parse", "HEAD"], cwd=cwd)
    if code != 0 or not head_sha:
        return 0

    slug = _repo_slug_from_remote(cwd) or _repo_slug_fallback(cwd)
    if _chronicle_exists(slug, head_sha):
        return 0

    code, subject = _run(["git", "log", "-1", "--format=%s", head_sha], cwd=cwd)
    subject = subject if code == 0 else ""

    hint = (
        "A git commit just completed — a chronicle entry should be captured while "
        "the session still holds the 'why' behind it.\n\n"
        f"  repo_slug: {slug}\n"
        f"  sha: {head_sha}\n"
        f"  subject: {subject}\n\n"
        "Invoke the `ghflow:chronicle` skill to record intent/decisions/tradeoffs "
        f"into ~/.commit-chronicles/{slug}/. "
        "If the current conversation genuinely has no meaningful context about this "
        "commit (e.g. the user committed unrelated work manually), you may skip "
        "writing — the skill itself will confirm before creating a sparse entry.\n\n"
        "This is a non-blocking nudge; do not stop current user-directed work to "
        "run it. Either finish the user's immediate ask then chronicle, or chronicle "
        "inline if the commit IS the user's immediate ask."
    )
    _emit(hint)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # never fail a tool call
        print(f"ghflow commit-chronicle hook: {e}", file=sys.stderr)
        sys.exit(0)
