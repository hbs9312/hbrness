"""Cheap regex pre-filter — skip turns that obviously aren't knowledge questions.

Goal: cut 70%+ of turns without touching an LLM. The judge LLM only sees
turns that pass this filter.

Heuristic: a "knowledge-worthy question" usually
  - is a *user* turn that contains a question shape, AND
  - asks about a concept/term/abbreviation rather than project-local state.

We deliberately err on the side of *keeping* ambiguous turns — false positives
just cost a Haiku judgment call (~$0.0005), false negatives lose data.
"""

from __future__ import annotations

import re

# Question shapes (Korean + English).
_QUESTION_PATTERNS = [
    re.compile(r"\?\s*$"),                    # trailing ?
    re.compile(r"(뭐야|뭐냐|뭐임|뭔데|뭐지)"),
    re.compile(r"(이란|이라는게|이라는|이라고|란\s)"),
    re.compile(r"(차이|다른점|뭐가\s*다)"),
    re.compile(r"(개념|의미|뜻|용어|약어)"),
    re.compile(r"(어떻게\s*동작|어떻게\s*작동|원리)"),
    re.compile(r"\bwhat\s+is\b", re.IGNORECASE),
    re.compile(r"\bwhat'?s\b", re.IGNORECASE),
    re.compile(r"\bdefine\b", re.IGNORECASE),
    re.compile(r"\bexplain\b", re.IGNORECASE),
    re.compile(r"\bdifference\s+between\b", re.IGNORECASE),
    re.compile(r"\bhow\s+does\b", re.IGNORECASE),
]

# Hard skip — these almost always indicate project-local/transient context.
_SKIP_PATTERNS = [
    re.compile(r"^/(?!kb-)\w"),               # leading slash command (skip non-kb skills)
    re.compile(r"(?i)^[!$]"),                 # bash escape prefix
    re.compile(r"^\s*<.*>\s*$", re.DOTALL),   # only system tags
]

# Project-local hints — terms suggesting it's about THIS code/repo, not general knowledge.
_PROJECT_LOCAL_HINTS = [
    re.compile(r"(이\s*프로젝트|우리\s*레포|이\s*레포|이\s*코드|이\s*파일|이\s*함수|이\s*폴더)"),
    re.compile(r"(?:^|\W)(this\s+(repo|project|file|function|folder|directory))(?:\W|$)", re.IGNORECASE),
    re.compile(r"@\w+\.(ts|tsx|js|jsx|py|go|rs|java|kt|md)\b"),  # file references
]


def is_knowledge_question(user_text: str) -> tuple[bool, str]:
    """Return (pass, reason). False reason = filter classification, not error."""
    if not user_text or not user_text.strip():
        return False, "empty"

    text = user_text.strip()

    # Hard skip first.
    for p in _SKIP_PATTERNS:
        if p.search(text):
            return False, "skip_pattern"

    # Length sanity — very long turns are usually code paste / discussion, not Q.
    if len(text) > 2000:
        return False, "too_long"

    # Must look like a question.
    if not any(p.search(text) for p in _QUESTION_PATTERNS):
        return False, "not_question"

    # Project-local hints downgrade — still pass but mark as low confidence.
    project_local = any(p.search(text) for p in _PROJECT_LOCAL_HINTS)
    if project_local:
        return True, "question_project_local"

    return True, "question_general"
