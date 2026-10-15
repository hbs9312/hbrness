#!/usr/bin/env python3
"""sfhook — sessionflow 훅 진입점. 바로 돌아오고 아무것도 출력하지 않는다 (에이전트 컨텍스트에 아무것도 넣지 않는다).

  python3 sfhook.py stop        --tool <claude|codex|grok|devin>   turn 끝: 뒤에서 state pull + transcript 수집
  python3 sfhook.py session-end --tool <…>                           세션 끝: 뒤에서 마지막 transcript 수집

stdin 의 훅 입력에서 session id, transcript 경로, cwd 를 읽는다. 도구마다 키 이름이 다르다.
  Claude·Codex·Devin   session_id / transcript_path / cwd
  Grok                 sessionId / cwd (transcript 경로는 주지 않는다 — sflog.py 가 찾는다), GROK_SESSION_ID
backend 가 없으면 아무것도 하지 않는다. 실제 일은 떼어 낸 프로세스(sfstate.py pull, sflog.py collect)가 한다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def hbrness_home() -> Path:
    return Path(os.environ.get("HBRNESS_HOME") or Path.home() / ".hbrness").expanduser()


def field(payload: dict, *names) -> str:
    for n in names:
        v = payload.get(n)
        if isinstance(v, str) and v:
            return v
    return ""


def spawn(args, cwd: str):
    subprocess.Popen([sys.executable, *map(str, args)], cwd=cwd if os.path.isdir(cwd) else None,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def run(event: str, tool: str, raw: str):
    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if not (hbrness_home() / "backend.json").exists():
        return
    session = field(payload, "session_id", "sessionId") or os.environ.get("GROK_SESSION_ID", "")
    transcript = field(payload, "transcript_path", "transcriptPath")
    cwd = (field(payload, "cwd", "workspaceRoot") or os.environ.get("CLAUDE_PROJECT_DIR")
           or os.environ.get("DEVIN_PROJECT_DIR") or os.getcwd())
    if event == "stop":
        spawn([HERE / "sfstate.py", "pull", "--dir", cwd], cwd)
    if session:
        args = [HERE / "sflog.py", "collect", "--tool", tool, "--session", session,
                "--transcript", transcript, "--cwd", cwd]
        spawn(args + (["--final"] if event == "session-end" else []), cwd)


def main(argv=None):
    p = argparse.ArgumentParser(prog="sfhook")
    p.add_argument("event", choices=["stop", "session-end"])
    p.add_argument("--tool", choices=["claude", "codex", "grok", "devin"], required=True)
    a = p.parse_args(argv)
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        run(a.event, a.tool, raw)
    except Exception:  # 훅은 절대 turn 을 깨뜨리지 않는다
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
