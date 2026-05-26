---
name: followup
description: "현재 세션에서 발견했지만 처리하지 못한 후속 조치 항목을 프로젝트 단위 FOLLOWUPS.md 에 누적 기록한다. handoff(세션 인계)와 달리 '나중에 처리해야 할 일' 의 영속 리스트이며, 워크트리·세션 무관하게 한 프로젝트당 하나의 파일을 공유한다. 사용자가 'followup', 'follow-up', 'followup 추가', '후속 조치', '나중에 처리할 일', '백로그 추가', '이번 세션 범위 밖', '미뤄둘 것', '/followup' 등을 말하면 트리거. Usage: /followup [-m | -o] [메시지]"
model: sonnet
---

# Followup Skill

이번 세션에서 발견했지만 **현재 세션의 범위를 벗어나** 별도로 처리해야 하는 항목을, 프로젝트 단위 `FOLLOWUPS.md` 에 **누적 기록**한다. 워크트리·세션·도구(Claude/Codex)와 무관하게 한 프로젝트당 하나의 파일을 공유한다.

`handoff` 와의 차이:

| | `followup` | `handoff` |
|---|---|---|
| 범위 | 프로젝트 단위 (영속·누적) | 워크트리/세션 단위 (1회성·in-flight) |
| 목적 | "나중에 처리해야 할 일" 백로그 | "지금 작업을 다음 세션이 그대로 이어받게" |
| 내용 | TODO·결정 보류·발견된 이슈·아이디어 | 마지막 명령·에러·편집중 파일·다음 한 줄 |
| 파일 | `FOLLOWUPS.md` (1 per project) | `HANDOFF.md` (1 per worktree) |

## 인자

`$ARGUMENTS` 또는 사용자 요청에서 파싱한다.

- `-m`: 기존 `FOLLOWUPS.md` 가 있으면 확인 없이 **merge** (기존 항목 + 이번에 추가할 항목).
- `-o`: 기존 `FOLLOWUPS.md` 가 있으면 확인 없이 **overwrite** (이번에 추가할 항목만 남김).
- 그 외 텍스트: 사용자가 함께 전달한 **추가 followup 컨텍스트** — 반영한다.

기본 동작은 **merge** 이다 (followup 은 본질적으로 누적되는 리스트이므로). 플래그가 없어도 사용자에게 묻지 않고 merge 한다. 명시적으로 비우고 싶을 때만 `-o`.

## 저장 경로

### FOLLOWUPS.md (Tier 1 — 도구 무관 공유, 프로젝트 단위)

```text
{HBRNESS_HOME}/sessionflow/<project-key>/FOLLOWUPS.md
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

워크트리에서 실행되더라도 원본 레포 루트를 사용한다 (followup 은 프로젝트 단위):

```bash
git_common=$(git rev-parse --git-common-dir 2>/dev/null) && project_root=$(cd "$(dirname "$git_common")" && pwd)
# git 레포가 아니면 project_root=$(pwd)
project_key=$(echo "$project_root" | tr '/' '-')
```

## 실행 흐름

### 1. 컨텍스트 수집

이번 세션에서 followup 으로 남길 만한 항목을 식별한다.

- 사용자가 명시적으로 "이건 followup 으로 남겨" 라고 한 항목.
- 이번 세션 대화에서 발견됐지만 처리하지 않고 넘어간 사항:
  - 발견된 버그·이슈 (지금 고치지 않음)
  - 보류된 결정 (사용자 확인 필요 / 정보 부족)
  - 아이디어·개선 제안
  - 의존성/선행 조건이 갖춰지지 않아 미룬 작업
  - 테스트·문서화 누락 항목
- 사용자가 `/followup` 과 함께 보낸 메시지.

세션 진행 상태(편집 중인 파일, 마지막 에러 등)는 followup 의 대상이 **아니다** — 그 정보는 `handoff` 스킬에 속한다.

비밀 값(env 파일·토큰·자격증명 등)은 절대 기록하지 않는다.

### 2. 기존 파일 처리

위 경로의 `FOLLOWUPS.md` 가 이미 있으면:

1. 읽는다.
2. 기존 항목과 이번에 추가할 항목을 비교한다.
3. 기본 동작: **merge** (기존 + 신규). 중복 항목은 제거. 항목 추가 시 발견 일자를 함께 남겨 추적성을 유지.
4. `-o` 가 명시되면 overwrite.

기존 파일이 없으면 새로 만든다.

### 3. FOLLOWUPS.md 작성

저장 디렉토리가 없으면 생성:

```bash
mkdir -p {HBRNESS_HOME}/sessionflow/<project-key>
```

다음 구조로 작성. 빈 섹션은 생략.

```markdown
# Project Followups

> Project: {project_root}
> Last updated: {현재 날짜·시간}

## Open

### {간결한 항목 제목}
- **Discovered**: {YYYY-MM-DD}
- **Context**: {왜 이게 followup 인지 — 어떤 상황에서 발견됐는지}
- **Action**: {필요한 다음 행동}
- **Refs**: {관련 파일·이슈·PR — 있으면}

### {다음 항목}
...

## Decisions Pending

### {결정이 필요한 주제}
- **Discovered**: {YYYY-MM-DD}
- **Options**: {고려 중인 대안}
- **Blocker**: {왜 지금 결정 못 했는지}

## Ideas / Improvements

- {YYYY-MM-DD} {짧은 아이디어 — 자세한 건 Open 으로 승격할 때 채움}

## Resolved (최근 N개)

- ~~{YYYY-MM-DD} {제목}~~ → resolved {YYYY-MM-DD}: {짧은 결과}
```

처리 완료된 항목은 즉시 삭제하지 말고 `Resolved` 섹션으로 옮긴다 (최근 10개까지만 유지, 그 이전은 잘라낸다). 이를 통해 "이미 다뤘던 followup 인지" 를 가볍게 추적할 수 있다.

### 4. 양쪽 MEMORY.md 갱신

같은 프로젝트에 대해 **두 위치 모두** 의 `MEMORY.md` 에 `## Followups` 섹션을 넣거나 갱신한다.

대상 경로:
- `{CLAUDE_MEMORY_PREFIX}/<project-key>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md`
- `{CODEX_MEMORY_PREFIX}/<project-key>{CODEX_MEMORY_SUFFIX}/MEMORY.md`

각 파일에 대해:
1. 파일이 존재하면 읽는다.
2. 이미 `## Followups` 섹션이 있으면 해당 섹션만 교체한다.
3. 없으면 파일 끝에 추가한다.
4. 파일 자체가 없으면 디렉토리 생성 후 새로 만든다.

추가/교체할 섹션 내용 (양쪽 동일):

```markdown
## Followups
- `{HBRNESS_HOME}/sessionflow/<project-key>/FOLLOWUPS.md` 에 프로젝트 후속 조치 항목 {N}개 누적 중 (최종 업데이트: {현재 날짜})
- 새 세션 시작 시 한 번 훑어 우선순위 판단에 참고. 작업 중 발견된 후속 항목은 `/followup` 으로 추가.
```

`<project-key>` 와 `{N}` 은 실제 값으로 치환한다.

### 5. 완료 보고

사용자에게 알린다:

- FOLLOWUPS.md 의 절대 경로
- 추가된 항목 수 / 전체 항목 수
- merge / overwrite / 신규 생성 여부
- 양쪽 MEMORY.md 갱신 여부

## 가이드라인

- followup 항목은 **구체적**이고 **검색 가능**해야 한다. "리팩터링 필요" 보다는 "auth middleware: session 만료 처리 누락 — login flow 에서 발견".
- 발견 일자를 반드시 기록 — 시간이 지나면 followup 의 적합성 자체가 흐려진다.
- "다음 세션에서 이어서 작업할 것" 은 followup 이 아니라 `handoff` 이다. 두 스킬을 혼동하지 말 것.
- Resolved 섹션은 짧게 유지 — 항목 archive 가 목적이지 history log 가 아니다.
