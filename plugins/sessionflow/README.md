# sessionflow

세션 간 컨텍스트를 보존·재개하기 위한 스킬 모음. Claude Code 와 Codex CLI 가 **동일한 HANDOFF.md 파일을 공유**하므로, 한 도구에서 작성한 핸드오프를 다른 도구에서 그대로 이어 작업할 수 있습니다.

## 스킬

| 스킬 | 트리거 | 역할 |
|---|---|---|
| `handoff` | `/handoff [-m\|-o] [메시지]` | 현재 세션 컨텍스트(작업 시도/성공/실패/현재 상태/TODO/주요 파일)를 `HANDOFF.md` 로 직렬화. 기존 파일이 있으면 merge(`-m`) 또는 overwrite(`-o`) 옵션. |
| `handoff-clear` | `/handoff-clear [-y]` | 핸드오프 작업이 완료되었을 때 `HANDOFF.md` 삭제 + 양쪽 `MEMORY.md` 의 `## Handoff` 섹션 제거. |

## 저장 경로 (Tier 1 — 도구 무관 공유)

```
~/.hbrness/sessionflow/<project-key>/HANDOFF.md
```

- `<project-key>` = 프로젝트 절대경로의 `/` 를 `-` 로 치환 (leading dash 유지). 예: `/Users/seok/development/my-app` → `-Users-seok-development-my-app`
- 양쪽 하네스에서 동일 파일을 읽고 씀.

## MEMORY.md 갱신 (Tier 2 — 하네스별 자동로드 위치)

스킬은 동시에 양쪽 하네스의 MEMORY.md 의 `## Handoff` 섹션을 갱신해 위 공유 경로를 가리키게 합니다. 두 위치는 각 하네스가 자동으로 컨텍스트에 로드하는 곳이므로 분리 유지가 필요합니다.

| 하네스 | MEMORY.md 위치 |
|---|---|
| Claude | `~/.claude/projects/<project-key>/memory/MEMORY.md` |
| Codex | `~/.codex/memories/<project-key>/MEMORY.md` |

스킬 본문은 `{CLAUDE_MEMORY_PREFIX}` / `{CLAUDE_MEMORY_SUFFIX}` 와
`{CODEX_MEMORY_PREFIX}` / `{CODEX_MEMORY_SUFFIX}` placeholder 로 양쪽 경로를 표현합니다.

## 동작 보장

- **install** 은 SKILL.md 만 배치합니다. MEMORY.md 는 `/handoff` 가 실제로 실행될 때만 갱신됩니다.
- 한 도구에서 `/handoff` 를 실행하면 같은 프로젝트의 양쪽 MEMORY.md (해당 도구가 접근 가능한 경우) 에 동일 경로 포인터가 들어갑니다.
- `handoff-clear` 는 양쪽 MEMORY.md 모두 정리합니다.
