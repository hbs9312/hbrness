---
name: followup-clear
description: "현재 프로젝트의 FOLLOWUPS.md 를 삭제하고, 양쪽 도구(Claude / Codex) MEMORY.md 의 Followups 섹션을 정리한다. 누적된 후속 조치 항목이 모두 처리됐거나 더 이상 유효하지 않아 한 번에 비우고 싶을 때 사용. 개별 항목만 해결하려면 followup 스킬의 Resolved 섹션 이동으로 충분하다. 사용자가 'clear followup', 'delete followup', 'reset followups', 'followup 정리', '후속 조치 비우기', '/followup-clear' 등을 말하면 트리거한다. Usage: /followup-clear [-y]"
model: sonnet
---

# Followup Clear Skill

`followup` 스킬이 만든 `FOLLOWUPS.md` 와 양쪽 도구 `MEMORY.md` 의 `## Followups` 섹션을 정리한다. 누적된 항목 전체를 한 번에 비우는 용도이며, 개별 항목 해결은 `/followup` 으로 Resolved 섹션에 옮기는 것으로 충분하다.

## 인자

- `-y`: 확인 없이 즉시 삭제.

## 대상 경로

`followup` 스킬과 동일하다.

### FOLLOWUPS.md (Tier 1 — 도구 무관 공유)

```text
{HBRNESS_HOME}/sessionflow/<project-key>/FOLLOWUPS.md
```

### MEMORY.md (Tier 2 — 양쪽 모두)

```text
{CLAUDE_MEMORY_PREFIX}/<project-key>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md
{CODEX_MEMORY_PREFIX}/<project-key>{CODEX_MEMORY_SUFFIX}/MEMORY.md
```

### `<project-key>` 도출

```bash
git_common=$(git rev-parse --git-common-dir 2>/dev/null) && project_root=$(cd "$(dirname "$git_common")" && pwd)
# git 레포가 아니면 project_root=$(pwd)
project_key=$(echo "$project_root" | tr '/' '-')
```

## 실행 흐름

### 1. FOLLOWUPS.md 위치 확인

위 경로에 `FOLLOWUPS.md` 가 존재하는지 검사한다.

- 없으면 사용자에게 "정리할 followup 이 없습니다" 라고 알리고 종료한다 (단, MEMORY.md 의 잔여 섹션도 추가로 정리한다 — Step 4 참고).

### 2. 요약과 확인

`FOLLOWUPS.md` 를 읽고 `Open` 섹션의 항목 수와 제목 목록을 사용자에게 보여준다.

- `-y` 가 있으면 그대로 진행.
- 없으면 사용자에게 삭제 여부를 확인받는다 ("Delete (Recommended)" / "Cancel").
- Open 항목이 5개 이상이면 추가로 한 번 더 경고한다 (실수 방지).

### 3. FOLLOWUPS.md 삭제

해당 프로젝트의 `FOLLOWUPS.md` 만 삭제한다. 절대 경로를 따옴표로 감싼다. 소스 레포 파일은 절대 건드리지 않는다.

```bash
rm "{HBRNESS_HOME}/sessionflow/<project-key>/FOLLOWUPS.md"
```

같은 디렉토리에 워크트리 핸드오프 (`worktrees/<wt>/HANDOFF.md`) 가 있을 수 있으나, 이 스킬은 절대 건드리지 않는다. 핸드오프 정리는 `handoff-clear` 스킬의 책임이다.

### 4. 양쪽 MEMORY.md 정리

대상 두 파일 각각에 대해:

1. 파일이 있으면 읽는다.
2. `## Followups` 섹션이 있으면 해당 헤딩부터 다음 `## ` 헤딩 직전까지(또는 파일 끝까지) 제거한다.
3. 다른 섹션 내용은 보존한다. 특히 `## Handoff` 섹션이 있다면 건드리지 않는다.
4. 정리 후 파일이 빈 줄/공백만 남으면 `MEMORY.md` 자체를 삭제한다.
5. 파일이 없거나 `## Followups` 섹션이 없으면 그 파일은 건너뛴다.

### 5. 완료 보고

사용자에게 알린다:

- FOLLOWUPS.md 가 삭제되었는지
- 어느 쪽 MEMORY.md 가 갱신/삭제되었는지
- (참고) 같은 프로젝트의 HANDOFF.md (있다면) 는 그대로 유지된다는 사실
