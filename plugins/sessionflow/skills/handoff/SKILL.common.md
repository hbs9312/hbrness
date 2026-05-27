---
name: handoff
description: "현재 워크트리/세션의 in-flight 컨텍스트(편집 중인 파일·마지막 실행 명령·실패한 에러·즉시 다음 한 줄)를 HANDOFF.md 로 직렬화한다. followup(프로젝트 단위 후속 조치)과 달리 '지금 작업을 다음 세션이 그대로 이어받는 것' 이 목적이며, 워크트리별로 파일이 분리된다. 사용자가 'handoff', 'hand off', '인계', '세션 끊김 대비', '이어서 작업', '컨텍스트 저장', 'save session context', 'prepare for next session', 'write HANDOFF.md', '핸드오프', 'handoff 남겨줘', '/handoff' 등을 말하면 트리거. Usage: /handoff [-m | -o] [메시지]"
model: sonnet
---

# Handoff Skill

현재 워크트리/세션의 **in-flight 컨텍스트** — 편집 중인 파일·마지막 실행 명령·실패한 에러·즉시 다음 한 줄 — 을 `HANDOFF.md` 에 기록하여, 다음 세션(Claude/Codex 어느 쪽이든)이 작업을 **그 자리에서 그대로** 이어받을 수 있게 한다. 워크트리별로 파일이 분리되므로, 같은 프로젝트의 여러 워크트리가 서로 덮어쓰지 않는다.

`followup` 과의 차이:

| | `handoff` | `followup` |
|---|---|---|
| 범위 | 워크트리/세션 단위 (1회성·in-flight) | 프로젝트 단위 (영속·누적) |
| 목적 | "지금 작업을 다음 세션이 그대로 이어받게" | "나중에 처리해야 할 일" 백로그 |
| 내용 | 마지막 명령·에러·편집중 파일·다음 한 줄 | TODO·결정 보류·발견된 이슈·아이디어 |
| 저장 | `HANDOFF.md` (1 per worktree) | `followups/INDEX.md` + 항목별 파일 (1 디렉토리 per project) |
| 수명 | 다음 세션에서 이어받으면 보통 삭제 | 항목별로 Resolved 처리하며 누적 |

## 인자

`$ARGUMENTS` 또는 사용자 요청에서 파싱한다.

- `-m`: 기존 `HANDOFF.md` 가 있으면 확인 없이 **merge** (이전 컨텍스트 + 이번 세션).
- `-o`: 기존 `HANDOFF.md` 가 있으면 확인 없이 **overwrite** (이번 세션만).
- 그 외 텍스트: 사용자가 함께 전달한 **추가 컨텍스트** — 핸드오프에 반영한다.

기본 동작: 기존 파일이 있으면 사용자에게 차이를 보여주고 **merge / overwrite / cancel** 중 선택을 받는다 (handoff 는 followup 과 달리 자동 merge 가 위험할 수 있음 — 이전 in-flight 상태가 이미 무효일 수 있기 때문).

## 저장 경로

### HANDOFF.md (Tier 1 — 도구 무관 공유, 워크트리 단위)

메인 레포(워크트리의 베이스 폴더)에서 실행하는 경우:

```text
{HBRNESS_HOME}/sessionflow/<project-key>/HANDOFF.md
```

워크트리에서 실행하는 경우:

```text
{HBRNESS_HOME}/sessionflow/<project-key>/worktrees/<wt-name>/HANDOFF.md
```

### MEMORY.md 갱신 위치 (양쪽 모두)

```text
{CLAUDE_MEMORY_PREFIX}/<project-key>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md
{CODEX_MEMORY_PREFIX}/<project-key>{CODEX_MEMORY_SUFFIX}/MEMORY.md
```

MEMORY.md 는 프로젝트 단위라 워크트리별로 별도 위치가 없다. 대신 섹션 내부에 "현재 활성 핸드오프 N개 (경로 목록)" 형태로 다중 워크트리를 표현한다.

### `<project-key>` 와 `<wt-name>` 도출

```bash
git_common=$(git rev-parse --git-common-dir 2>/dev/null)
git_dir=$(git rev-parse --git-dir 2>/dev/null)

if [ -z "$git_common" ]; then
  # git 레포가 아님
  project_root=$(pwd)
  is_worktree=0
else
  # 원본 레포 루트
  project_root=$(cd "$(dirname "$git_common")" && pwd)
  if [ "$git_dir" = "$git_common" ]; then
    # 메인 레포 (git_dir 과 git_common_dir 이 동일)
    is_worktree=0
  else
    # 워크트리: git_dir = .git/worktrees/<wt-name>
    is_worktree=1
    wt_name=$(basename "$git_dir")
  fi
fi

project_key=$(echo "$project_root" | tr '/' '-')

if [ "$is_worktree" = "1" ]; then
  handoff_path="{HBRNESS_HOME}/sessionflow/$project_key/worktrees/$wt_name/HANDOFF.md"
else
  handoff_path="{HBRNESS_HOME}/sessionflow/$project_key/HANDOFF.md"
fi
```

## 실행 흐름

### 1. 컨텍스트 수집

다음 세션이 작업을 즉시 이어받는 데 필요한 in-flight 사실을 모은다.

- 현재 working directory · 현재 날짜/시간 · 활성 브랜치 · 워크트리 여부와 이름.
- `git status --short`, `git diff --stat`, `git diff`, `git diff --cached --stat`, `git diff --cached`.
- 추적되지 않은 파일: `git ls-files --others --exclude-standard`.
- 대화 컨텍스트:
  - 이번 세션에서 시도한 행동·실행한 명령
  - 마지막으로 실행한 명령과 그 결과 (실패면 에러 메시지 원문)
  - 편집 중이던 파일과 어디까지 진행했는지 (파일:줄 단위로 구체)
  - 다음에 즉시 실행해야 할 단 한 가지
- 사용자가 `/handoff` 와 함께 보낸 메시지.

세션의 거시적 TODO 나 백로그성 항목은 handoff 의 대상이 **아니다** — 그 정보는 `followup` 스킬에 속한다.

비밀 값(env 파일·토큰·자격증명 등)은 절대 기록하지 않는다.

### 2. 기존 파일 처리

위 경로의 `HANDOFF.md` 가 이미 있으면:

1. 읽는다.
2. 여전히 유효한 이전 컨텍스트(예: 같은 작업을 이어가는 중)인지, 무효(다른 작업으로 전환)인지 식별.
3. `-m` → merge, `-o` → overwrite 로 즉시 진행.
4. 플래그가 없으면 사용자에게 차이를 요약해서 보여주고 **merge / overwrite / cancel** 중 선택하게 한다.

기존 파일이 없으면 그냥 진행.

### 3. HANDOFF.md 작성

저장 디렉토리가 없으면 생성:

```bash
mkdir -p "$(dirname "$handoff_path")"
```

빈 섹션은 생략하고 다음 구조로 간결하게 작성한다:

```markdown
# Session Handoff

> Generated: {현재 날짜·시간}
> Working Directory: {project_root}
> Worktree: {wt_name 또는 "main"}
> Branch: {활성 브랜치}

## Context

{이번 세션이 무엇을 하던 중이었는지 한두 문장. /handoff 메시지가 있으면 포함.}

## Last Command

```
{직전에 실행한 명령}
```

{명령의 stdout/stderr 요약 또는 에러 메시지 원문 — 실패한 경우 특히 중요.}

## In-Flight Edits

- `{파일경로}:{줄번호}` — {무엇을 하던 중인지, 어디까지 적용했는지}

## Current State

{git status 요약: 브랜치, staged/unstaged/untracked. 빌드/테스트 상태가 있으면 함께.}

## Next Action

{다음 세션이 즉시 실행해야 할 단 한 가지. 명령과 함께 적는다.}

```
{재현 명령}
```

## Notes

{환경 변수·실행 중인 프로세스·임시 가정. 다음 세션이 모르면 막힐 만한 것만.}
```

`Next Action` 은 가능한 한 **하나** 만 적는다. 여러 개 떠올랐다면 가장 즉시 필요한 것 하나만 여기에 두고, 나머지는 followup 으로 이관하라고 보고에 언급한다.

### 4. 양쪽 MEMORY.md 갱신

같은 프로젝트에 대해 **두 위치 모두** 의 `MEMORY.md` 에 `## Handoff` 섹션을 넣거나 갱신한다.

대상 경로:
- `{CLAUDE_MEMORY_PREFIX}/<project-key>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md`
- `{CODEX_MEMORY_PREFIX}/<project-key>{CODEX_MEMORY_SUFFIX}/MEMORY.md`

각 파일에 대해:
1. 파일이 존재하면 읽는다.
2. 이미 `## Handoff` 섹션이 있으면 다음 규칙으로 병합:
   - 같은 워크트리(또는 메인)의 핸드오프 라인이 이미 있으면 갱신.
   - 다른 워크트리의 핸드오프 라인은 그대로 보존.
3. 섹션이 없으면 파일 끝에 추가.
4. 파일 자체가 없으면 디렉토리 생성 후 새로 만든다.

추가/교체할 섹션 내용 (양쪽 동일):

```markdown
## Handoff
활성 세션 핸드오프:
- {main 또는 worktrees/<wt-name>}: `<handoff_path>` (최종 업데이트: {현재 날짜})
새 세션 시작 시 현재 working directory 와 일치하는 핸드오프를 읽어 작업을 이어간다.
```

활성 핸드오프가 여러 워크트리에 걸쳐 있을 수 있으므로 라인을 **추가** 하는 식으로 관리한다.

### 5. 완료 보고

사용자에게 알린다:

- HANDOFF.md 의 절대 경로
- 메인 레포인지 / 워크트리인지 (워크트리면 이름)
- 새로 만들어졌는지 / merge 됐는지 / overwrite 됐는지
- 캡처한 Next Action 한 줄 요약
- 양쪽 MEMORY.md 갱신 여부
- (있다면) followup 으로 옮기는 게 더 맞을 항목들에 대한 제안

## 가이드라인

- 새 세션이 전체 대화 로그를 다시 읽지 않고도 **그 자리에서** 작업을 재개할 수 있도록 구체적으로.
- 모호한 표현 대신 파일:줄, 명령 원문, 에러 메시지 원문을 사용.
- "다음 작업 후보 N개" 처럼 백로그 성격이면 followup 스킬 사용을 권하라.
- 워크트리에서 호출됐을 때 메인 레포 핸드오프를 건드리지 말 것 (반대도 마찬가지).
- 비밀 값은 절대 포함하지 말 것.
