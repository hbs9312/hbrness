#!/usr/bin/env python3
"""llm-kb background worker.

Receives a normalized Turn payload on stdin (written by ``kb-judge.py``),
asks an LLM to judge whether the turn yields a knowledge-base-worthy concept,
and if so writes the entry as a single Korean markdown file in
``~/.hbrness/llm-kb/entries/``.

Hard rules baked into the judge prompt:
    - Output language **must always be Korean**, even when the source concept
      is in English. Original term is bracketed alongside the Korean form.
    - Project-local context (this repo / this file / "여기서는") never gets
      saved — judge must classify as ``project_local`` and we drop it.
    - Sensitive content (credentials, tokens, internal hostnames, customer
      data) must never be saved — judge must redact or skip.

LLM access:
    Prefers the ``claude`` CLI which inherits the user's existing login
    session, runs the cheapest model (Haiku 4.5), and forwards a
    ``LLM_KB_WORKER=1`` env so any recursive Stop hooks self-terminate.
    Falls back to ``ANTHROPIC_API_KEY`` direct HTTP if the CLI isn't on
    PATH. If neither is available, logs and exits — never blocks.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

from lib import store  # noqa: E402

JUDGE_MODEL = "claude-haiku-4-5"
JUDGE_TIMEOUT = 60  # seconds — generous, runs in background

JUDGE_PROMPT = """\
당신은 사용자의 개인 지식 베이스(LLM Wiki) 큐레이터다.
방금 끝난 1턴(사용자 질문 + 어시스턴트 답변)을 받아 KB에 저장할 가치가 있는지 판단한다.

## 입력
사용자가 어시스턴트에게 한 마지막 질문, 그리고 어시스턴트의 답변이 함께 주어진다.

## 절대 규칙
1. **언어는 무조건 한국어**. 원어 개념은 한국어 설명 + 괄호 안에 원어 병기.
2. **프로젝트 한정 내용은 저장 금지**. "이 프로젝트", "이 파일", "이 함수", "여기서는" 처럼 특정 코드/레포에 묶인 것은 `project_local` 로 분류하고 skip.
3. **민감 정보 금지**. credential, API key, 토큰, 내부 호스트명, 고객 데이터, 회사 내부 시스템명이 답변에 들어 있으면 skip 또는 해당 부분을 redact.
4. **이미 일반인이 다 아는 상식은 skip**. (예: "변수가 뭐야", "if 문")
5. **하나의 개념**만 추출. 답변이 여러 개념을 다뤘다면 가장 핵심인 하나만.

## 분류
다음 중 하나를 정한다:
- `save` — 일반/도메인 지식. KB에 저장.
- `project_local` — 이 프로젝트/코드 한정. skip.
- `too_trivial` — 누구나 아는 상식. skip.
- `sensitive` — 민감 정보 포함. skip.
- `not_a_concept` — 사실 개념 질문이 아니었음. skip.

## save 일 때 출력 스키마
JSON 한 덩어리만 출력한다. 다른 텍스트 금지.

```json
{
  "decision": "save",
  "name": "한국어 표제 (원어)",
  "slug": "kebab-ascii-slug",
  "description": "한 줄 요약 (한국어, 80자 이내)",
  "domain": ["주-도메인", "선택-부도메인"],
  "aliases": ["원어", "다른 한국어 표기"],
  "body": "한국어 본문. 정의 → 핵심 메커니즘/사용 맥락 → (있으면) 비교/관련 개념. 마크다운 허용. 600자 이내."
}
```

## skip 일 때 출력
```json
{ "decision": "<project_local|too_trivial|sensitive|not_a_concept>", "reason": "한국어 한 줄" }
```

## 입력 데이터
USER_QUESTION:
{USER_QUESTION}

ASSISTANT_ANSWER:
{ASSISTANT_ANSWER}

위 규칙에 따라 JSON 한 덩어리만 출력한다.
"""


def _build_prompt(turn: dict) -> str:
    user = (turn.get("user_text") or "").strip()
    asst = (turn.get("assistant_text") or "").strip()
    # Bound input to keep judge cost predictable.
    if len(user) > 1500:
        user = user[:1500] + "…"
    if len(asst) > 4000:
        asst = asst[:4000] + "…"
    return JUDGE_PROMPT.replace("{USER_QUESTION}", user).replace("{ASSISTANT_ANSWER}", asst)


def _call_claude_cli(prompt: str) -> str | None:
    """Invoke ``claude -p`` headless. Returns assistant text or None."""
    if not shutil.which("claude"):
        return None
    env = os.environ.copy()
    env["LLM_KB_WORKER"] = "1"  # propagate guard

    try:
        proc = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", JUDGE_MODEL,
                "--output-format", "json",
            ],
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        store.log("claude CLI timeout")
        return None
    except Exception as e:
        store.log(f"claude CLI exec failed: {e}")
        return None

    if proc.returncode != 0:
        store.log(f"claude CLI rc={proc.returncode} stderr={proc.stderr[:300]}")
        return None

    # claude -p --output-format json => {"result": "...", ...}
    try:
        data = json.loads(proc.stdout)
        return data.get("result") or proc.stdout
    except json.JSONDecodeError:
        return proc.stdout


def _call_anthropic_api(prompt: str) -> str | None:
    """Fallback: direct API call using ANTHROPIC_API_KEY."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    body = json.dumps({
        "model": JUDGE_MODEL,
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=JUDGE_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        store.log(f"api call failed: {e}")
        return None

    blocks = payload.get("content") or []
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "\n".join(parts).strip() or None


def _extract_json(text: str) -> dict | None:
    """Find a single top-level JSON object in the model output."""
    if not text:
        return None
    # Direct parse attempt
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fenced ```json ... ``` block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # First {...} balanced brace match (greedy fallback)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _render_entry(verdict: dict, source: str) -> tuple[str, str]:
    """Build (slug, full_markdown_text) from a saveable verdict."""
    import datetime as _dt

    name = (verdict.get("name") or "").strip() or "Untitled"
    slug = store.slugify(verdict.get("slug") or name)
    description = (verdict.get("description") or "").strip().replace("\n", " ")
    domain = verdict.get("domain") or ["misc"]
    if isinstance(domain, str):
        domain = [domain]
    aliases = verdict.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    body = (verdict.get("body") or "").strip()

    now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).isoformat(timespec="seconds")

    # If the entry already exists, preserve created_at; bump updated_at.
    existing = store.read_entry(slug)
    created_at = now
    if existing and existing.startswith("---"):
        for line in existing.splitlines()[:30]:
            if line.startswith("created_at:"):
                created_at = line.split(":", 1)[1].strip().strip('"').strip("'") or now
                break

    fm_lines = [
        "---",
        f"name: \"{name}\"",
        f"slug: {slug}",
        f"description: \"{description}\"",
        "domain:",
        *(f"  - {d}" for d in domain),
    ]
    if aliases:
        fm_lines.append("aliases:")
        fm_lines.extend(f"  - \"{a}\"" for a in aliases)
    fm_lines.extend([
        "lang: ko",
        f"source: {source}",
        f"created_at: {created_at}",
        f"updated_at: {now}",
        "---",
        "",
    ])

    md = "\n".join(fm_lines) + f"# {name}\n\n{body}\n"
    return slug, md


def main() -> int:
    try:
        raw = sys.stdin.read()
        turn = json.loads(raw) if raw else {}
    except Exception as e:
        store.log(f"worker bad stdin: {e}")
        return 0

    if not turn.get("user_text") or not turn.get("assistant_text"):
        return 0

    if store.is_disabled():
        return 0

    prompt = _build_prompt(turn)
    raw_response = _call_claude_cli(prompt) or _call_anthropic_api(prompt)
    if not raw_response:
        store.log("no LLM available — skip")
        return 0

    verdict = _extract_json(raw_response)
    if not verdict or not isinstance(verdict, dict):
        store.log(f"unparseable verdict: {raw_response[:200]}")
        return 0

    decision = (verdict.get("decision") or "").strip()
    if decision != "save":
        reason = verdict.get("reason", "")
        store.log(f"skip ({decision}): {reason}")
        return 0

    if not verdict.get("name") or not verdict.get("body"):
        store.log("save verdict missing name/body — skip")
        return 0

    source = turn.get("harness", "unknown")
    slug, md = _render_entry(verdict, source)
    try:
        path = store.write_entry(slug, md)
        store.update_index()
        store.log(f"saved: {slug} ← {turn.get('filter_reason', '?')} (cwd={turn.get('cwd', '')})")
    except Exception as e:
        store.log(f"write failed for {slug}: {e}")
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        try:
            store.log(f"worker fatal: {e}")
        except Exception:
            pass
        sys.exit(0)
