---
name: handoff-clear
description: "현재 워크트리(또는 메인 레포)의 HANDOFF.md 를 삭제하고, 양쪽 도구(Claude / Codex) MEMORY.md 의 Handoff 섹션에서 해당 라인을 정리한다. 핸드오프에 적힌 작업이 끝나 다음 세션에서 이어받을 필요가 없을 때 사용. 사용자가 'clear handoff', 'delete handoff', 'remove handoff', 'handoff done', 'handoff complete', '핸드오프 삭제', '핸드오프 정리', '/handoff-clear' 등을 말하면 트리거한다. Usage: /handoff-clear [-y] [--all]"
model: sonnet
---

# Handoff Clear Skill

`handoff` 스킬이 만든 `HANDOFF.md` 와 양쪽 도구 `MEMORY.md` 의 `## Handoff` 섹션에서 해당 라인을 정리한다. 기본은 **현재 위치(워크트리 또는 메인)** 의 핸드오프만 정리한다.

## 인자

- `-y`: 확인 없이 즉시 삭제.
- `--all`: 현재 프로젝트의 **모든** 워크트리 핸드오프 + 메인 핸드오프를 한 번에 정리. 단독 `-y` 와 조합 시 무확인 진행.

## 대상 경로

`handoff` 스킬과 동일하다.

### HANDOFF.md (Tier 1)

메인 레포에서 실행:
```text
{HBRNESS_HOME}/sessionflow/<project-key>/HANDOFF.md
```

워크트리에서 실행:
```text
{HBRNESS_HOME}/sessionflow/<project-key>/worktrees/<wt-name>/HANDOFF.md
```

`--all` 일 때:
```text
{HBRNESS_HOME}/sessionflow/<project-key>/HANDOFF.md
{HBRNESS_HOME}/sessionflow/<project-key>/worktrees/*/HANDOFF.md
```

### MEMORY.md (Tier 2 — 양쪽 모두)

```text
{CLAUDE_MEMORY_PREFIX}/<project-key>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md
{CODEX_MEMORY_PREFIX}/<project-key>{CODEX_MEMORY_SUFFIX}/MEMORY.md
```

### `<project-key>` 와 `<wt-name>` 도출

```bash
git_common=$(git rev-parse --git-common-dir 2>/dev/null)
git_dir=$(git rev-parse --git-dir 2>/dev/null)

if [ -z "$git_common" ]; then
  project_root=$(pwd)
  is_worktree=0
else
  project_root=$(cd "$(dirname "$git_common")" && pwd)
  if [ "$git_dir" = "$git_common" ]; then
    is_worktree=0
  else
    is_worktree=1
    wt_name=$(basename "$git_dir")
  fi
fi

project_key=$(echo "$project_root" | tr '/' '-')
```

## 실행 흐름

### 1. 대상 핸드오프 결정

- `--all` 없음 + 메인 레포: `<project-key>/HANDOFF.md` 만
- `--all` 없음 + 워크트리: `<project-key>/worktrees/<wt-name>/HANDOFF.md` 만
- `--all`: 위 두 종류 모두 (메인 + 모든 워크트리)

### 2. 존재 확인

대상 경로에 파일이 하나도 없으면 사용자에게 "정리할 핸드오프가 없습니다" 라고 알리고 종료한다 (단, MEMORY.md 의 잔여 라인도 추가로 정리 — Step 4 참고).

### 3. 요약과 확인

각 핸드오프의 `Next Action` (또는 그에 준하는 마지막 메모) 을 사용자에게 보여준다.

- `-y` 가 있으면 그대로 진행.
- 없으면 사용자에게 삭제 여부를 확인받는다 ("Delete (Recommended)" / "Cancel").
- `--all` 인 경우, 삭제될 핸드오프 수가 1개를 넘으면 한 번 더 경고한다.

### 4. HANDOFF.md 삭제

대상 파일을 삭제. 절대 경로를 따옴표로 감싼다. 소스 레포 파일은 절대 건드리지 않는다.

```bash
rm "$path"
```

워크트리 핸드오프를 삭제한 뒤 `worktrees/<wt-name>/` 디렉토리가 비었으면 그 디렉토리도 제거 (rmdir, 실패해도 무시).

같은 프로젝트의 `followups/` 디렉토리는 절대 건드리지 않는다 — followup 정리는 `followup-clear` 의 책임이다.

### 5. 양쪽 MEMORY.md 정리

대상 두 파일 각각에 대해:

1. 파일이 있으면 읽는다.
2. `## Handoff` 섹션 내부에서 삭제된 핸드오프에 해당하는 라인만 제거한다.
   - 핸드오프 경로(절대경로) 가 라인에 포함된 경우를 매칭 기준으로 한다.
3. `## Handoff` 섹션에 활성 핸드오프 라인이 더 이상 남지 않으면 섹션 자체를 제거한다 (헤딩 ~ 다음 `## ` 직전).
4. 다른 섹션 내용은 보존한다. 특히 `## Followups` 섹션이 있다면 건드리지 않는다.
5. 정리 후 파일이 빈 줄/공백만 남으면 `MEMORY.md` 자체를 삭제한다.
6. 파일이 없거나 `## Handoff` 섹션이 없으면 그 파일은 건너뛴다.

### 6. 완료 보고

사용자에게 알린다:

- 삭제된 HANDOFF.md 절대경로 목록
- 어느 쪽 MEMORY.md 가 갱신/삭제되었는지
- (참고) 같은 프로젝트의 followups/ 디렉토리 (있다면) 는 그대로 유지된다는 사실
