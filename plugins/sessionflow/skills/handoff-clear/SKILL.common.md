---
name: handoff-clear
description: "현재 프로젝트의 통합 HANDOFF.md 를 삭제하고, 양쪽 도구(Claude / Codex) MEMORY.md 의 Handoff 섹션을 정리한다. 핸드오프에 적힌 작업이 끝났을 때 사용. 사용자가 'clear handoff', 'delete handoff', 'remove handoff', 'handoff done', 'handoff complete', '핸드오프 삭제', '핸드오프 정리', '/handoff-clear' 등을 말하면 트리거한다. Usage: /handoff-clear [-y]"
model: sonnet
---

# Handoff Clear Skill

`handoff` 스킬이 만든 통합 `HANDOFF.md` 와 양쪽 도구 `MEMORY.md` 의 `## Handoff` 섹션을 정리한다.

## 인자

- `-y`: 확인 없이 즉시 삭제.

## 대상 경로

`handoff` 스킬과 동일하다.

### HANDOFF.md (Tier 1 — 도구 무관 공유)

```text
{HBRNESS_HOME}/sessionflow/<project-key>/HANDOFF.md
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

### 1. HANDOFF.md 위치 확인

위 경로에 `HANDOFF.md` 가 존재하는지 검사한다.

- 없으면 사용자에게 "정리할 핸드오프가 없습니다" 라고 알리고 종료한다 (단, MEMORY.md 의 잔여 섹션도 추가로 정리한다 — Step 4 참고).

### 2. 요약과 확인

`HANDOFF.md` 를 읽고 `TODO` 섹션(또는 가까운 남은 작업) 을 사용자에게 보여준다.

- `-y` 가 있으면 그대로 진행.
- 없으면 사용자에게 삭제 여부를 확인받는다 ("Delete (Recommended)" / "Cancel").

### 3. HANDOFF.md 삭제

해당 프로젝트의 `HANDOFF.md` 만 삭제한다. 절대 경로를 따옴표로 감싼다. 소스 레포 파일은 절대 건드리지 않는다.

```bash
rm "{HBRNESS_HOME}/sessionflow/<project-key>/HANDOFF.md"
```

### 4. 양쪽 MEMORY.md 정리

대상 두 파일 각각에 대해:

1. 파일이 있으면 읽는다.
2. `## Handoff` 섹션이 있으면 해당 헤딩부터 다음 `## ` 헤딩 직전까지(또는 파일 끝까지) 제거한다.
3. 다른 섹션 내용은 보존한다.
4. 정리 후 파일이 빈 줄/공백만 남으면 `MEMORY.md` 자체를 삭제한다.
5. 파일이 없거나 `## Handoff` 섹션이 없으면 그 파일은 건너뛴다.

### 5. 완료 보고

사용자에게 알린다:

- HANDOFF.md 가 삭제되었는지
- 어느 쪽 MEMORY.md 가 갱신/삭제되었는지
