---
name: followup
description: "현재 세션에서 발견했지만 처리하지 못한 후속 조치 항목을, 프로젝트 단위 followups 디렉토리(INDEX.md + 항목별 상세 파일)에 누적 기록한다. handoff(세션 인계)와 달리 '나중에 처리해야 할 일' 의 영속 리스트이며, 워크트리·세션 무관하게 한 프로젝트당 하나의 디렉토리를 공유한다. 사용자가 'followup', 'follow-up', 'followup 추가', '후속 조치', '나중에 처리할 일', '백로그 추가', '이번 세션 범위 밖', '미뤄둘 것', '/followup' 등을 말하면 트리거. Usage: /followup [-m | -o] [메시지]"
model: sonnet
---

# Followup Skill

이번 세션에서 발견했지만 **현재 세션의 범위를 벗어나** 별도로 처리해야 하는 항목을, 프로젝트 단위 `followups/` 디렉토리에 **누적 기록**한다. 워크트리·세션·도구(Claude/Codex)와 무관하게 한 프로젝트당 하나의 디렉토리를 공유한다.

항목 수가 늘어도 한 파일이 비대해지지 않도록, 항목 목록·검색용 **`INDEX.md`** 와 항목별 **상세 파일** 로 분할한다. 에이전트는 `INDEX.md` 만 가볍게 훑어 관련 항목을 고르고, 필요한 상세 파일만 열어 본다.

`handoff` 와의 차이:

| | `followup` | `handoff` |
|---|---|---|
| 범위 | 프로젝트 단위 (영속·누적) | 워크트리/세션 단위 (1회성·in-flight) |
| 목적 | "나중에 처리해야 할 일" 백로그 | "지금 작업을 다음 세션이 그대로 이어받게" |
| 내용 | TODO·결정 보류·발견된 이슈·아이디어 | 마지막 명령·에러·편집중 파일·다음 한 줄 |
| 저장 | `followups/INDEX.md` + 항목별 파일 (1 디렉토리 per project) | `HANDOFF.md` (1 per worktree) |

## 인자

`$ARGUMENTS` 또는 사용자 요청에서 파싱한다.

- `-m`: 기존 항목이 있으면 확인 없이 **merge** (기존 항목 유지 + 이번에 추가/갱신할 항목).
- `-o`: 기존 항목이 있으면 확인 없이 **overwrite** (`followups/` 를 비우고 이번에 추가할 항목만 남김).
- 그 외 텍스트: 사용자가 함께 전달한 **추가 followup 컨텍스트** — 반영한다.

기본 동작은 **merge** 이다 (followup 은 본질적으로 누적되는 리스트이므로). 플래그가 없어도 사용자에게 묻지 않고 merge 한다. 명시적으로 비우고 싶을 때만 `-o`.

## 저장 경로

### followups/ 디렉토리 (Tier 1 — 도구 무관 공유, 프로젝트 단위)

```text
{HBRNESS_HOME}/sessionflow/<project-key>/followups/
├── INDEX.md            # 항목 목록 + 한 줄 설명 + 상세 파일 링크 (에이전트 진입점)
├── <slug>.md           # 항목별 상세 파일
└── <slug>.md
```

같은 디렉토리(`{HBRNESS_HOME}/sessionflow/<project-key>/`)에는 `HANDOFF.md` 와 `worktrees/` 가 공존할 수 있으나, 이 스킬은 `followups/` 하위만 다룬다. 핸드오프는 절대 건드리지 않는다.

### 레거시 단일 파일 (마이그레이션 대상)

이전 버전은 프로젝트당 단일 `FOLLOWUPS.md` 를 사용했다:

```text
{HBRNESS_HOME}/sessionflow/<project-key>/FOLLOWUPS.md
```

이 파일이 존재하면 Step 2 에서 새 구조로 마이그레이션한다.

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

## 항목 ↔ 상세 파일 규칙

- **슬러그(파일명)**: 항목 제목에서 도출한 짧은 kebab-case. 영문이 자연스러우면 영문, 아니면 핵심 키워드를 간결하게. 공백·`/` 는 `-` 로. 길게 늘이지 말 것 (대략 5단어 이내). 예: `auth-session-expiry.md`, `api-rate-limit.md`.
- **충돌**: 같은 슬러그가 이미 있으면 `-2`, `-3` 을 붙인다.
- **1 항목 = 1 파일**: `Open`·`Decisions Pending` 항목은 각각 상세 파일을 갖는다.
- **Ideas 는 파일 없이** `INDEX.md` 에 한 줄로만 적는다 (한 줄짜리에 파일을 만들지 않는다). `Open` 으로 승격될 때 비로소 상세 파일을 만든다.

## 상세 파일 형식

각 항목 파일은 frontmatter + 본문으로 구성한다:

```markdown
---
title: {간결한 항목 제목}
status: open            # open | pending | resolved
discovered: {YYYY-MM-DD}
resolved:               # resolved 일 때만 {YYYY-MM-DD}, 아니면 비움
refs:                   # 관련 파일·이슈·PR (선택, 리스트)
  - {경로 또는 #이슈}
---

# {제목}

## Context
{왜 이게 followup 인지 — 어떤 상황에서 발견됐는지}

## Action
{필요한 다음 행동. status: pending 이면 이 섹션 대신 Options / Blocker 사용}

## Notes
{추가 메모·진행 로그 — 선택. 시간이 지나며 덧붙인다}
```

`status: pending` (결정 보류) 항목은 `## Action` 대신:

```markdown
## Options
{고려 중인 대안}

## Blocker
{왜 지금 결정 못 했는지}
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

### 2. 기존 구조 파악 + 레거시 마이그레이션

`followups/` 디렉토리와 레거시 `FOLLOWUPS.md` 의 존재 여부를 확인한다.

```bash
ls "{HBRNESS_HOME}/sessionflow/<project-key>/followups/INDEX.md" 2>/dev/null
ls "{HBRNESS_HOME}/sessionflow/<project-key>/FOLLOWUPS.md" 2>/dev/null
```

분기:

1. **`followups/INDEX.md` 가 있으면**: 읽어서 현재 항목 목록을 파악한다. 갱신할 항목의 상세 파일도 필요한 만큼 읽는다.
2. **`followups/` 는 없고 레거시 `FOLLOWUPS.md` 만 있으면 — 마이그레이션**:
   - 레거시 파일을 읽는다.
   - `Open` / `Decisions Pending` 의 각 항목을 새 상세 파일(`<slug>.md`)로 변환한다 (위 상세 파일 형식). 기존의 Discovered·Context·Action·Refs 를 frontmatter/본문에 매핑한다.
   - `Ideas / Improvements` 한 줄 항목들은 `INDEX.md` 의 Ideas 섹션으로 그대로 옮긴다 (파일 미생성).
   - `Resolved` 항목들은 `INDEX.md` 의 Resolved 섹션으로 옮긴다 (상세 파일은 만들지 않고 제목·날짜만).
   - 변환이 끝나면 레거시 `FOLLOWUPS.md` 를 삭제한다 (`rm "<...>/FOLLOWUPS.md"`).
   - 사용자에게 "레거시 단일 파일을 새 구조로 마이그레이션함" 을 보고에 포함한다.
3. **둘 다 없으면**: 새로 만든다.

`-o` 가 명시된 경우: 마이그레이션을 건너뛰고 기존 `followups/` 내용과 레거시 파일을 무시한 채 이번 항목만으로 새로 쓴다 (Step 5 에서 기존 디렉토리를 비운다).

### 3. 디렉토리 준비

```bash
mkdir -p "{HBRNESS_HOME}/sessionflow/<project-key>/followups"
```

`-o` 인 경우 기존 상세 파일을 먼저 정리한다 (절대 경로 따옴표 필수, `followups/` 하위만):

```bash
rm -f "{HBRNESS_HOME}/sessionflow/<project-key>/followups/"*.md
```

### 4. 항목별 상세 파일 작성/갱신

이번에 추가·갱신할 각 항목에 대해:

- 신규 항목: 슬러그를 정하고 `followups/<slug>.md` 를 위 형식으로 만든다.
- 기존 항목 갱신(merge): 같은 항목이면 해당 상세 파일의 `## Notes` 에 덧붙이거나 본문을 갱신한다. 중복 신규 파일을 만들지 않는다.
- 해결된 항목: 상세 파일의 frontmatter 를 `status: resolved` + `resolved: {YYYY-MM-DD}` 로 바꾸고, 본문 끝에 짧은 결과를 남긴다. 파일은 유지하되 `INDEX.md` 에서는 Resolved 섹션으로 이동한다.
- Ideas(한 줄): 상세 파일을 만들지 않는다. Step 5 에서 `INDEX.md` 의 Ideas 섹션에만 적는다.

발견 일자(`discovered`)는 반드시 기록한다.

### 5. INDEX.md 작성/갱신

`followups/INDEX.md` 를 다음 구조로 쓴다. 빈 섹션은 생략. 상세 파일 링크는 같은 디렉토리 기준 상대경로(`./<slug>.md`).

```markdown
# Project Followups — Index

> Project: {project_root}
> Last updated: {현재 날짜·시간}
> Open: {n} · Pending: {n} · Resolved: {n}

## Open

| 제목 | 한 줄 설명 | Discovered | 상세 |
|---|---|---|---|
| {제목} | {에이전트가 관련성을 판단할 한 줄 설명} | {YYYY-MM-DD} | [{slug}.md](./{slug}.md) |

## Decisions Pending

| 주제 | 한 줄 설명 | Discovered | 상세 |
|---|---|---|---|
| {주제} | {무엇을 결정해야 하는지 한 줄} | {YYYY-MM-DD} | [{slug}.md](./{slug}.md) |

## Ideas / Improvements

- {YYYY-MM-DD} {짧은 아이디어 — 상세 파일 없음. Open 승격 시 파일 생성}

## Resolved (최근 10)

| 제목 | Resolved | 상세 |
|---|---|---|
| ~~{제목}~~ | {YYYY-MM-DD} | [{slug}.md](./{slug}.md) |
```

- 한 줄 설명은 **검색·판별용** 이다. 상세 내용을 반복하지 말고, 에이전트가 "이 항목을 열어볼지" 결정할 단서만 적는다.
- 해결된 항목은 즉시 삭제하지 말고 Resolved 섹션으로 옮긴다. **최근 10개까지만** 유지하고, 그보다 오래된 것은 INDEX 행과 해당 상세 파일을 함께 삭제한다.

### 6. 양쪽 MEMORY.md 갱신

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
- `{HBRNESS_HOME}/sessionflow/<project-key>/followups/INDEX.md` 에 프로젝트 후속 조치 {N}개 누적 중 (최종 업데이트: {현재 날짜})
- 새 세션 시작 시 INDEX.md 를 한 번 훑어 우선순위 판단에 참고하고, 필요한 항목의 상세 파일만 연다. 작업 중 발견된 후속 항목은 `/followup` 으로 추가.
```

`<project-key>` 와 `{N}`(= Open + Pending 합계) 은 실제 값으로 치환한다.

### 7. 완료 보고

사용자에게 알린다:

- `followups/INDEX.md` 의 절대 경로
- 추가/갱신된 항목 수 / 전체 Open·Pending 항목 수
- 새로 만든 상세 파일 슬러그 목록
- merge / overwrite / 신규 생성 여부 (+ 레거시 마이그레이션 수행 시 그 사실)
- 양쪽 MEMORY.md 갱신 여부

## 가이드라인

- followup 항목은 **구체적**이고 **검색 가능**해야 한다. "리팩터링 필요" 보다는 "auth middleware: session 만료 처리 누락 — login flow 에서 발견".
- `INDEX.md` 는 가볍게 유지한다 — 한 줄 설명과 링크만. 본문은 상세 파일이 책임진다.
- 발견 일자를 반드시 기록 — 시간이 지나면 followup 의 적합성 자체가 흐려진다.
- "다음 세션에서 이어서 작업할 것" 은 followup 이 아니라 `handoff` 이다. 두 스킬을 혼동하지 말 것.
- Resolved 는 짧게 유지 — 항목 archive 가 목적이지 history log 가 아니다 (최근 10개).
