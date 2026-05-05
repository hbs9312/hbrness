#!/usr/bin/env python3
"""llm-kb Stop hook entrypoint.

Fires whenever the host harness emits a Stop event. Job:

    1. Bail fast if we're inside a recursive harness session that we ourselves
       spawned (env guard) or the harness's own ``stop_hook_active`` flag is
       set.
    2. Read stdin JSON, normalize to a common Turn shape regardless of
       harness (claude/codex).
    3. Apply a cheap regex pre-filter — most turns are not knowledge questions
       and we want to skip the LLM call entirely for those.
    4. If the turn passes filtering, hand off to ``kb-worker.py`` as a fully
       detached background process and exit immediately. The worker does the
       LLM judgment + write so this hook never blocks the next user input.

We never raise on errors — Stop hooks must not break user flow. All failures
are swallowed and logged to ``~/.hbrness/llm-kb/worker.log``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

from lib import normalizer, prefilter, store  # noqa: E402


def _read_stdin_json() -> dict:
    try:
        data = sys.stdin.read()
        if not data:
            return {}
        return json.loads(data)
    except Exception:
        return {}


def _detect_harness(payload: dict) -> str:
    """Best-effort harness detection from payload shape."""
    # Caller may pass it explicitly via env (set by adapter hooks.json)
    h = os.environ.get("LLM_KB_HARNESS", "").strip().lower()
    if h in ("claude", "codex"):
        return h
    # Heuristic fallback
    if "transcript_path" in payload and isinstance(payload.get("transcript_path"), str):
        path = payload["transcript_path"]
        if "/.codex/" in path or "/codex/" in path:
            return "codex"
        return "claude"
    if "rollout_path" in payload:
        return "codex"
    return "claude"


def _spawn_worker(turn: dict) -> None:
    """Detach a background worker process and return immediately."""
    worker_path = HOOK_DIR / "kb-worker.py"
    if not worker_path.is_file():
        store.log("worker script missing — skip")
        return

    env = os.environ.copy()
    env["LLM_KB_WORKER"] = "1"          # primary recursion guard
    env.pop("LLM_KB_HARNESS", None)      # don't leak host harness into worker subprocesses

    payload = json.dumps(turn, ensure_ascii=False)

    try:
        proc = subprocess.Popen(
            ["python3", str(worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            close_fds=True,
            start_new_session=True,      # fully detach from this hook process
        )
        # Write payload then close to release the worker.
        if proc.stdin:
            proc.stdin.write(payload.encode("utf-8"))
            proc.stdin.close()
    except Exception as e:
        store.log(f"spawn failed: {e}")


def main() -> int:
    # Guard 1: recursive worker session.
    if os.environ.get("LLM_KB_WORKER") == "1":
        return 0

    # Guard 2: kill switch.
    if store.is_disabled():
        return 0

    payload = _read_stdin_json()

    # Guard 3: harness's own recursion flag.
    if payload.get("stop_hook_active") is True:
        return 0

    harness = _detect_harness(payload)
    turn = normalizer.normalize(payload, harness)
    if turn is None:
        return 0

    if turn.get("stop_hook_active"):
        return 0

    user_text = turn.get("user_text") or ""
    ok, reason = prefilter.is_knowledge_question(user_text)
    if not ok:
        return 0

    turn["filter_reason"] = reason
    _spawn_worker(turn)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # never break the host
        try:
            store.log(f"kb-judge fatal: {e}")
        except Exception:
            pass
        sys.exit(0)
