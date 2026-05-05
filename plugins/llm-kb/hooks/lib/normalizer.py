"""Normalize Stop-event payloads from different harnesses into a common shape.

Both Claude Code and Codex CLI provide stdin JSON when a Stop hook fires, but
the schema differs. This module exposes ``normalize(payload, harness)`` that
returns a uniform ``Turn`` dict regardless of source.

Output schema::

    {
        "user_text":      str,            # last user message text
        "assistant_text": str,            # last assistant response text
        "cwd":            str,            # working directory
        "session_id":     str,            # opaque session id (for dedup)
        "stop_hook_active": bool,         # recursion flag if provided
        "harness":        str,            # "claude" | "codex"
    }

Returns ``None`` if the payload doesn't contain a usable user/assistant pair.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _read_jsonl_tail(path: str, max_lines: int = 200) -> list[dict]:
    """Read the last ``max_lines`` JSON objects from a JSONL file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []

    out: list[dict] = []
    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _extract_text_from_content(content: Any) -> str:
    """Content blocks may be str or list of {type, text, ...}. Flatten to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("type")
                if t in ("text", "input_text", "output_text") and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                # Skip tool_use / tool_result / thinking blocks
        return "\n".join(parts).strip()
    return ""


def _normalize_claude(payload: dict) -> dict | None:
    transcript_path = payload.get("transcript_path")
    if not transcript_path or not os.path.isfile(transcript_path):
        return None

    entries = _read_jsonl_tail(transcript_path)
    if not entries:
        return None

    # Walk backwards: find last assistant, then preceding user.
    last_assistant = None
    last_user = None
    for entry in reversed(entries):
        msg = entry.get("message") or {}
        role = msg.get("role") or entry.get("type")
        if role == "assistant" and last_assistant is None:
            last_assistant = _extract_text_from_content(msg.get("content", entry.get("content", "")))
        elif role == "user" and last_assistant is not None and last_user is None:
            content = _extract_text_from_content(msg.get("content", entry.get("content", "")))
            # Skip tool-result-only user turns.
            if content.strip():
                last_user = content
                break

    if not last_user or not last_assistant:
        return None

    return {
        "user_text": last_user,
        "assistant_text": last_assistant,
        "cwd": payload.get("cwd") or os.getcwd(),
        "session_id": payload.get("session_id", ""),
        "stop_hook_active": bool(payload.get("stop_hook_active", False)),
        "harness": "claude",
    }


def _normalize_codex(payload: dict) -> dict | None:
    """Codex Stop event normalizer.

    Codex's exact Stop payload schema is still evolving; this implementation
    is best-effort. We accept either:
      - a transcript_path style payload (same as Claude), or
      - an inline ``last_user_message`` / ``last_assistant_message`` pair.
    """
    # Prefer inline form if present.
    inline_user = payload.get("last_user_message") or payload.get("user_message")
    inline_asst = payload.get("last_assistant_message") or payload.get("assistant_message")
    if inline_user and inline_asst:
        return {
            "user_text": _extract_text_from_content(inline_user),
            "assistant_text": _extract_text_from_content(inline_asst),
            "cwd": payload.get("cwd") or os.getcwd(),
            "session_id": payload.get("session_id", ""),
            "stop_hook_active": bool(payload.get("stop_hook_active", False)),
            "harness": "codex",
        }

    # Fall back to transcript_path form.
    transcript_path = payload.get("transcript_path") or payload.get("rollout_path")
    if transcript_path and os.path.isfile(transcript_path):
        result = _normalize_codex_rollout(transcript_path, payload)
        if result:
            return result
        # Reuse claude-style JSONL parsing if format matches.
        result = _normalize_claude({
            "transcript_path": transcript_path,
            "cwd": payload.get("cwd"),
            "session_id": payload.get("session_id", ""),
            "stop_hook_active": payload.get("stop_hook_active", False),
        })
        if result:
            result["harness"] = "codex"
            return result

    return None


def _looks_like_environment_context(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("<environment_context>") and stripped.endswith("</environment_context>")


def _extract_codex_payload_text(payload: dict) -> str:
    ptype = payload.get("type")
    if ptype == "user_message" and isinstance(payload.get("message"), str):
        return payload["message"].strip()
    if ptype == "agent_message" and isinstance(payload.get("message"), str):
        return payload["message"].strip()
    if ptype == "message":
        return _extract_text_from_content(payload.get("content", "")).strip()
    return ""


def _normalize_codex_rollout(path: str, hook_payload: dict) -> dict | None:
    """Parse Codex rollout JSONL files from ``~/.codex/sessions/...``.

    Current Codex session logs are not Claude-style ``message.role`` JSONL.
    They are envelope records with a ``payload`` object, e.g.:

      - ``event_msg`` / ``payload.type == "user_message"``
      - ``response_item`` / ``payload.type == "message"`` / ``role == "assistant"``

    We pair the latest user message with the latest assistant response after
    it, preferring the final-phase response over commentary updates.
    """
    entries = _read_jsonl_tail(path, max_lines=600)
    if not entries:
        return None

    cwd = hook_payload.get("cwd") or os.getcwd()
    session_id = hook_payload.get("session_id", "")
    stop_hook_active = bool(hook_payload.get("stop_hook_active", False))

    current_user = ""
    assistant_after_user: list[tuple[str, str]] = []

    for entry in entries:
        etype = entry.get("type")
        if etype == "turn_context":
            cwd = entry.get("cwd") or cwd
            continue
        if etype == "session_meta":
            cwd = entry.get("cwd") or cwd
            session_id = entry.get("id") or session_id
            continue

        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue

        ptype = payload.get("type")

        is_user = (
            (etype == "event_msg" and ptype == "user_message")
            or (etype == "response_item" and ptype == "message" and payload.get("role") == "user")
        )
        if is_user:
            text = _extract_codex_payload_text(payload)
            if text and not _looks_like_environment_context(text):
                current_user = text
                assistant_after_user = []
            continue

        is_assistant = (
            etype == "response_item"
            and ptype == "message"
            and payload.get("role") == "assistant"
        )
        if is_assistant and current_user:
            text = _extract_codex_payload_text(payload)
            if text:
                assistant_after_user.append((payload.get("phase") or "", text))

    if not current_user or not assistant_after_user:
        return None

    final_texts = [text for phase, text in assistant_after_user if phase == "final"]
    assistant_text = final_texts[-1] if final_texts else assistant_after_user[-1][1]

    return {
        "user_text": current_user,
        "assistant_text": assistant_text,
        "cwd": cwd,
        "session_id": session_id,
        "stop_hook_active": stop_hook_active,
        "harness": "codex",
    }


def normalize(payload: dict, harness: str) -> dict | None:
    """Normalize a Stop-hook stdin payload to the common Turn schema."""
    harness = harness.lower()
    if harness == "claude":
        return _normalize_claude(payload)
    if harness == "codex":
        return _normalize_codex(payload)
    return None


def project_key(cwd: str) -> str:
    """Convert absolute path to dash-separated project key (sessionflow convention)."""
    abs_path = str(Path(cwd).resolve())
    return abs_path.replace("/", "-")
