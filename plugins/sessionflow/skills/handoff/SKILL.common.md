---
name: handoff
description: "현재 세션의 컨텍스트(작업 시도/성공/실패/현재 상태/TODO/주요 파일)를 도구 무관 단일 HANDOFF.md 파일로 직렬화한다. Claude 와 Codex 가 같은 파일을 읽고 쓰므로, 한 도구에서 작성한 핸드오프를 다른 도구에서 그대로 이어받을 수 있다. 사용자가 'handoff', 'hand off', 'create handoff', 'save session context', 'prepare for next session', 'write HANDOFF.md', 'save progress for next session', '핸드오프', 'handoff 남겨줘', '/handoff' 등을 말하면 트리거한다. Usage: /handoff [-m | -o] [메시지]"
model: sonnet
---

# Handoff Skill

현재 세션의 작업 흐름·결정·다음 단계를 **도구 무관 공유 위치**의 `HANDOFF.md` 에 기록하여, 다음 세션(Claude / Codex 어느 쪽이든) 이 컨텍스트를 잃지 않고 작업을 이어갈 수 있게 한다.

## 인자

`$ARGUMENTS` 또는 사용자 요청에서 파싱한다.

- `-m`: 기존 `HANDOFF.md` 가 있으면 확인 없이 **merge** (이전 컨텍스트 + 이번 세션).
- `-o`: 기존 `HANDOFF.md` 가 있으면 확인 없이 **overwrite** (이번 세션만).
- 그 외 텍스트: 사용자가 함께 전달한 **추가 컨텍스트** — 핸드오프에 반영한다.

## 저장 경로

### HANDOFF.md (Tier 1 — 도구 무관 공유)

```text
{HBRNESS_HOME}/sessionflow/<project-key>/HANDOFF.md
```

### MEMORY.md 갱신 위치 (양쪽 모두)

```text
{CLAUDE_MEMORY_PREFIX}/<project-key>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md
{CODEX_MEMORY_PREFIX}/<project-key>{CODEX_MEMORY_SUFFIX}/MEMORY.md
```

### `<project-key>` 도출

현재 working directory 의 **절대 경로** 에서 `/` 를 `-` 로 치환한다. **leading dash 유지**.

```text
/Users/seok/development/my-app
→ -Users-seok-development-my-app
```

워크트리에서 실행되더라도 원본 레포 루트를 사용한다:

```bash
git_common=$(git rev-parse --git-common-dir 2>/dev/null) && project_root=$(cd "$(dirname "$git_common")" && pwd)
# git 레포가 아니면 project_root=$(pwd)
project_key=$(echo "$project_root" | tr '/' '-')
```

## 실행 흐름

### 1. 컨텍스트 수집

새 세션이 그대로 이어가는 데 필요한 사실을 모은다.

- 현재 working directory · 현재 날짜/시간 · 활성 브랜치(가능하면).
- `git status --short`, `git diff --stat`, `git diff`, `git diff --cached --stat`, `git diff --cached`. git 레포가 아니면 그 사실을 명시.
- 추적되지 않은 파일: `git ls-files --others --exclude-standard` (레포일 때).
- 최근 커밋 스타일: `git log --oneline -5` (필요 시).
- 대화 컨텍스트: 최초 요청 · 의미있는 결정 · 만진 파일 · 실행한 명령 · 성공한 것 · 실패한 것 · 남은 작업.
- 사용자가 `/handoff` 와 함께 보낸 메시지.

비밀 값(env 파일 · 토큰 · 자격증명 등)을 발견하면 핸드오프에 **포함하지 말 것**. 누락했다는 사실만 명시한다.

### 2. 기존 파일 처리

위 경로의 `HANDOFF.md` 가 이미 있으면:

1. 읽는다.
2. 여전히 유효한 이전 컨텍스트와 TODO 를 식별한다.
3. `-m` → merge, `-o` → overwrite 로 즉시 진행.
4. 플래그가 없으면 사용자에게 차이를 요약해서 보여주고 **merge / overwrite / cancel** 중 선택하게 한다.

기존 파일이 없으면 그냥 진행.

### 3. HANDOFF.md 작성

저장 디렉토리가 없으면 생성한다:

```bash
mkdir -p {HBRNESS_HOME}/sessionflow/<project-key>
```

빈 섹션은 생략하고 다음 구조로 간결하게 작성한다:

```markdown
# Session Handoff

> Generated: {현재 날짜·시간}
> Working Directory: {project_root}

## Context

{사용자 요청과 세션 목적의 짧은 요약. /handoff 메시지가 있으면 포함.}

## What Was Tried

- {시도한 행동·명령·접근·핵심 결정}

## What Succeeded

- {적용된 변경, 통과한 검사·테스트}

## What Failed

- {에러·차단 상황·실패한 시도·포기한 접근}

## Current State

{git status 요약, 브랜치, staged/unstaged/untracked, 주요 런타임 상태.}

## TODO

- [ ] {구체적 다음 행동}

## Key Files

- `{경로}` — {왜 중요한지}

## Notes

{환경 세팅, 가정, 주의사항.}
```

### 4. 양쪽 MEMORY.md 갱신

같은 프로젝트에 대해 **두 위치 모두** 의 `MEMORY.md` 에 `## Handoff` 섹션을 넣거나 갱신한다. 디렉토리가 없으면 생성한다.

대상 경로:
- `{CLAUDE_MEMORY_PREFIX}/<project-key>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md`
- `{CODEX_MEMORY_PREFIX}/<project-key>{CODEX_MEMORY_SUFFIX}/MEMORY.md`

각 파일에 대해:
1. 파일이 존재하면 읽는다.
2. 이미 `## Handoff` 섹션이 있으면 해당 섹션만 교체한다 (다른 섹션은 그대로).
3. 없으면 파일 끝에 추가한다.
4. 파일 자체가 없으면 디렉토리 생성 후 새로 만든다.

추가/교체할 섹션 내용 (양쪽 동일):

```markdown
## Handoff
- `{HBRNESS_HOME}/sessionflow/<project-key>/HANDOFF.md` 존재함 (최종 업데이트: {현재 날짜})
- 새 세션 시작 시 반드시 읽어서 컨텍스트를 파악할 것
```

`<project-key>` 자리는 실제 값으로 치환해서 쓴다.

### 5. 완료 보고

사용자에게 알린다:

- HANDOFF.md 의 절대 경로
- 새로 만들어졌는지 / merge 됐는지 / overwrite 됐는지
- 캡처한 주요 내용 한 줄 요약
- 양쪽 MEMORY.md 갱신 여부

## 가이드라인

- 새 세션이 전체 대화 로그를 다시 읽지 않고도 맥락을 잡을 수 있도록 **간결하지만 충분하게**.
- 모호한 표현 대신 구체적 파일 경로 · 명령 · 에러 메시지를 사용.
- 이전 핸드오프에서 가져오는 컨텍스트는 명확히 구분.
- TODO 섹션이 가장 중요 — 구체적이고 우선순위 있게.
