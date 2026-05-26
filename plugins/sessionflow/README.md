# sessionflow

세션 간 컨텍스트를 보존·재개하기 위한 스킬 모음. Claude Code 와 Codex CLI 가 **동일한 파일(`HANDOFF.md` / `FOLLOWUPS.md`)을 공유**하므로, 한 도구에서 작성한 내용을 다른 도구에서 그대로 이어 작업할 수 있습니다.

## 스킬

| 스킬 | 트리거 | 역할 | 범위 |
|---|---|---|---|
| `followup` | `/followup [-m\|-o] [메시지]` | 현재 세션에서 발견한 **후속 조치** 항목을 `FOLLOWUPS.md` 에 누적 기록. TODO·결정 보류·아이디어·발견된 이슈. 기본 동작은 merge. | 프로젝트 단위 (워크트리·세션 무관) |
| `followup-clear` | `/followup-clear [-y]` | 누적된 followup 을 한 번에 비움. `FOLLOWUPS.md` 삭제 + 양쪽 `MEMORY.md` 의 `## Followups` 섹션 제거. | 프로젝트 단위 |
| `handoff` | `/handoff [-m\|-o] [메시지]` | 현재 워크트리/세션의 **in-flight 컨텍스트** (편집중 파일·마지막 명령·실패한 에러·다음 한 줄) 를 `HANDOFF.md` 로 직렬화. 다음 세션이 즉시 이어받을 수 있게. | 워크트리 단위 (메인 = 워크트리의 베이스) |
| `handoff-clear` | `/handoff-clear [-y] [--all]` | 현재 위치(워크트리/메인)의 `HANDOFF.md` 삭제 + `MEMORY.md` 의 해당 라인 정리. `--all` 로 프로젝트 전체 핸드오프 일괄 정리. | 워크트리 단위 (또는 `--all` 시 프로젝트 전체) |

## followup vs handoff — 언제 무엇을 쓰는가

| | `followup` | `handoff` |
|---|---|---|
| 시나리오 | "이 버그 발견했는데 이번엔 못 고치겠다 — 나중에 처리해야 됨" | "지금 빌드 에러 잡는 중인데 컨텍스트 길어져서 끊김 — 새 세션에서 그대로 이어가야 함" |
| 누가 읽나 | 다음 세션 시작 시점, 또는 백로그 정리 시점 | 바로 다음 세션 — 그 자리에서 작업 재개 |
| 수명 | 항목별로 Resolved 처리하며 영속 누적 | 작업 재개 후 보통 삭제 |
| 파일 | `FOLLOWUPS.md` (1 per project) | `HANDOFF.md` (1 per worktree) |

## 저장 경로 (Tier 1 — 도구 무관 공유)

```
~/.hbrness/sessionflow/<project-key>/
├── FOLLOWUPS.md                          # 프로젝트 단위
├── HANDOFF.md                            # 메인 레포에서 호출한 핸드오프
└── worktrees/
    └── <wt-name>/HANDOFF.md              # 각 워크트리별 핸드오프
```

- `<project-key>` = 프로젝트 절대경로의 `/` 를 `-` 로 치환 (leading dash 유지).
  예: `/Users/seok/development/my-app` → `-Users-seok-development-my-app`
- `<wt-name>` = `basename "$(git rev-parse --git-dir)"` — git 워크트리 디렉토리명
- 양쪽 하네스(Claude / Codex)에서 동일 파일을 읽고 씀.

## MEMORY.md 갱신 (Tier 2 — 하네스별 자동로드 위치)

스킬은 동시에 양쪽 하네스의 MEMORY.md 의 `## Followups` 또는 `## Handoff` 섹션을 갱신해 위 공유 경로를 가리키게 합니다.

| 하네스 | MEMORY.md 위치 |
|---|---|
| Claude | `~/.claude/projects/<project-key>/memory/MEMORY.md` |
| Codex | `~/.codex/memories/<project-key>/MEMORY.md` |

스킬 본문은 `{CLAUDE_MEMORY_PREFIX}` / `{CLAUDE_MEMORY_SUFFIX}` 와 `{CODEX_MEMORY_PREFIX}` / `{CODEX_MEMORY_SUFFIX}` placeholder 로 양쪽 경로를 표현합니다.

## 동작 보장

- **install** 은 SKILL.md 만 배치합니다. MEMORY.md 는 스킬이 실제로 실행될 때만 갱신됩니다.
- `followup` 과 `handoff` 는 서로의 파일을 절대 건드리지 않습니다. clear 스킬도 마찬가지입니다.
- `handoff` 는 워크트리 격리 — 같은 프로젝트의 메인/워크트리A/워크트리B 가 서로 덮어쓰지 않습니다.
- `followup` 은 프로젝트 단위 — 어느 워크트리에서 호출해도 동일한 `FOLLOWUPS.md` 에 누적됩니다.
