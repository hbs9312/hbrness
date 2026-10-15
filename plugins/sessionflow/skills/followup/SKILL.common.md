---
name: followup
description: "현재 세션에서 발견했지만 처리하지 못한 후속 조치 항목을, 저장소 단위 followups 디렉토리(항목별 상세 파일 + 생성되는 INDEX.md)에 누적 기록하고, private state repo 로 여러 PC 사이에 동기화한다. handoff(세션 인계)와 달리 '나중에 처리해야 할 일' 의 영속 리스트이며, 워크트리·세션·PC 와 무관하게 같은 저장소(origin remote)면 하나의 디렉토리를 공유한다. 사용자가 'followup', 'follow-up', 'followup 추가', '후속 조치', '나중에 처리할 일', '백로그 추가', '이번 세션 범위 밖', '미뤄둘 것', '/followup' 등을 말하면 트리거. 'followup 목록', '후속 조치 뭐 남았어' 처럼 현황을 물으면 list 로 동작. Usage: /followup [list | -m | -o] [메시지]"
model: sonnet
---

# Followup Skill

이번 세션에서 발견했지만 **현재 세션의 범위를 벗어나** 별도로 처리해야 하는 항목을, 저장소 단위 `followups/` 디렉토리에 **누적 기록**한다. 워크트리·세션·도구(Claude/Codex/Grok/Devin)·PC 와 무관하게 **같은 저장소면 같은 디렉토리**를 쓴다. 저장소는 경로가 아니라 origin remote URL 로 가린다 — 회사 PC 와 집 PC 에서 clone 경로가 달라도 같은 목록을 본다.

항목마다 **상세 파일 하나**를 두고, 목록용 **`INDEX.md` 는 항목 파일의 frontmatter 로 스크립트가 만든다.** 에이전트는 `INDEX.md` 만 가볍게 훑어 관련 항목을 고르고, 필요한 상세 파일만 열어 본다.

`handoff` 와의 차이:

| | `followup` | `handoff` |
|---|---|---|
| 범위 | 저장소 단위 (영속·누적) | 저장소 + 브랜치 단위 (1회성·in-flight) |
| 목적 | "나중에 처리해야 할 일" 백로그 | "지금 작업을 다음 세션이 그대로 이어받게" |
| 내용 | TODO·결정 보류·발견된 이슈·아이디어 | 마지막 명령·에러·편집중 파일·다음 한 줄 |
| 저장 | `followups/<slug>.md` (+ 생성되는 `INDEX.md`) | `handoffs/<branch>.md` |

## 스크립트

경로 계산·pull·push·INDEX 생성은 전부 `sfstate.py` 가 한다. 이 문서에서 `SF` 는 다음 명령을 뜻한다:

```bash
python3 "${SKILL_DIR}/../../scripts/sfstate.py"
```

- `SF prepare` — 로컬 state 를 원격과 맞추고(pull), 예전 경로 기준 데이터가 있으면 옮기고, `INDEX.md` 를 만든 뒤 경로를 `KEY=VALUE` 로 출력한다.
- `SF sync -m "<메시지>"` — `INDEX.md` 를 다시 만들고(오래된 resolved 정리 포함) 이 저장소의 변경만 원격에 올린다. 원격은 `backend.json` 이 있으면 backend, 없으면 state repo(commit + push)다.
- `SF status` — 이 저장소의 핸드오프·followup 현황을 짧게 보여준다.

`prepare` 출력에서 쓰는 값:

| 키 | 뜻 |
|---|---|
| `FOLLOWUPS_DIR` | 항목 파일을 쓰는 디렉토리 |
| `INDEX_FILE` | 생성된 INDEX.md (읽기 전용으로 취급) |
| `REPO_KEY` | 저장소 키 (예: `github.com/hbs9312/hbrness`). 비면 remote 가 없는 프로젝트 |
| `SYNC` | `on` 이면 push 까지 된다. `off` 면 이 PC 에만 저장 (`SYNC_NOTE` 에 이유) |
| `MEMORY_KEY` | MEMORY.md 경로에 쓰는 키 |
| `LEGACY_SINGLE` | 아주 예전 단일 `FOLLOWUPS.md` 를 옮겨 둔 파일. 비어 있지 않으면 Step 2 에서 항목으로 나눈다 |

`SYNC=off` 여도 기록은 된다. 사용자에게 `SYNC_NOTE` 를 한 줄로 알리기만 하고 계속한다.

`prepare`·`sync` 출력에 `CONFLICT=<상대경로> → <경로>` 줄이 있으면, 다른 PC 가 같은 파일을 먼저 바꾼 것이다. 원격본을 원래 자리에 받았고 이 PC 의 버전은 화살표 오른쪽 경로(`_conflicts/` 아래)에 남겼다. 사용자에게 두 파일을 알리고, 합칠지 원격본을 그대로 둘지 묻는다. 합치면 원래 자리의 파일을 고치고 다시 sync 한 뒤 `_conflicts/` 의 파일을 지운다.

## 인자

`$ARGUMENTS` 또는 사용자 요청에서 파싱한다.

- `list`: 현황만 보여주고 끝낸다 (아래 "list" 절).
- `-m`: 기존 항목이 있으면 확인 없이 **merge** (기존 항목 유지 + 이번에 추가/갱신할 항목).
- `-o`: 기존 항목이 있으면 확인 없이 **overwrite** (`followups/` 의 항목 파일을 비우고 이번에 추가할 항목만 남김).
- 그 외 텍스트: 사용자가 함께 전달한 **추가 followup 컨텍스트** — 반영한다.

기본 동작은 **merge** 이다 (followup 은 본질적으로 누적되는 리스트이므로). 플래그가 없어도 사용자에게 묻지 않고 merge 한다. 명시적으로 비우고 싶을 때만 `-o`.

## 저장 경로

```text
~/.hbrness/state/                       # private state repo 의 clone (PC 마다 하나)
└── <host>/<owner>/<repo>/              # REPO_KEY — origin remote URL 을 정규화한 값
    ├── followups/
    │   ├── INDEX.md                    # 생성물. git 추적 안 함. 직접 고치지 않는다
    │   ├── _config.json                # 선택: {"resolved_keep": 10}
    │   └── <slug>.md                   # 항목 하나 = 파일 하나 (frontmatter 가 진실원)
    └── handoffs/<branch>.md            # handoff 스킬 영역 — 이 스킬은 건드리지 않는다
```

remote 가 없는 프로젝트는 `~/.hbrness/state/_local/<경로키>/` 에 저장되고 동기화되지 않는다.

## 항목 ↔ 상세 파일 규칙

- **슬러그(파일명)**: 항목 제목에서 도출한 짧은 kebab-case. 영문이 자연스러우면 영문, 아니면 핵심 키워드를 간결하게. 공백·`/` 는 `-` 로. 길게 늘이지 말 것 (대략 5단어 이내). 예: `auth-session-expiry.md`, `api-rate-limit.md`. `_` 로 시작하는 이름은 쓰지 않는다 (스크립트가 항목이 아닌 파일로 본다).
- **충돌**: 같은 슬러그가 이미 있으면 `-2`, `-3` 을 붙인다.
- **1 항목 = 1 파일**: Open · Pending · Idea 모두 파일을 갖는다. 아이디어도 짧은 파일 하나로 둔다 — 두 PC 가 한 파일에 줄을 덧붙이면 충돌하기 때문이다.

## 상세 파일 형식

```markdown
---
title: {간결한 항목 제목}
summary: "{INDEX 에 보일 한 줄 설명 — 에이전트가 열어볼지 판단할 단서}"
status: open            # open | pending | idea | resolved
discovered: {YYYY-MM-DD}
resolved:               # resolved 일 때만 {YYYY-MM-DD}
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

- `summary` 는 **INDEX 의 '한 줄 설명' 칸**이 된다. 진행 상황이 바뀌면 INDEX 가 아니라 이 값을 고친다. 따옴표로 감싼다(콜론·`#` 이 들어가도 안전하게).
- `status: pending` (결정 보류) 항목은 `## Action` 대신 `## Options` / `## Blocker` 를 쓴다.
- `status: idea` 항목은 frontmatter 와 제목 한 줄이면 충분하다.

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

비밀 값(env 파일·토큰·자격증명 등)은 절대 기록하지 않는다. state repo 는 원격에 push 된다.

### 2. 준비 — pull + 기존 구조 파악

```bash
SF prepare
```

- `MIGRATE=migrated` 가 보이면 이 PC 의 예전 경로 기준 followup·핸드오프를 저장소 기준으로 옮긴 것이다. 보고에 한 줄로 넣는다. 예전 파일은 지우지 않고 그대로 둔다.
- `PULL=failed` 면 네트워크·인증 문제다. 로컬 사본으로 계속하고 보고에 남긴다.
- `INDEX_FILE` 이 있으면 읽어서 현재 항목 목록을 파악한다. 갱신할 항목의 상세 파일도 필요한 만큼 읽는다.
- `LEGACY_SINGLE` 이 비어 있지 않으면 — 아주 예전 단일 `FOLLOWUPS.md` 형식이다:
  - 그 파일을 읽어 `Open` / `Decisions Pending` 각 항목을 상세 파일(`<slug>.md`)로, `Ideas / Improvements` 한 줄 항목들을 `status: idea` 파일로 만든다. `Resolved` 항목은 버린다.
  - 다 옮기면 `LEGACY_SINGLE` 파일을 지운다.

`-o` 인 경우: 기존 항목을 무시하고 이번 항목만으로 새로 쓴다 (Step 3 에서 비운다).

### 3. 항목별 상세 파일 작성/갱신

`-o` 인 경우 먼저 기존 항목 파일을 지운다 (`FOLLOWUPS_DIR` 하위의 `*.md` 만, 절대 경로 따옴표 필수):

```bash
rm -f "<FOLLOWUPS_DIR>/"*.md
```

이번에 추가·갱신할 각 항목에 대해:

- 신규 항목: 슬러그를 정하고 `<FOLLOWUPS_DIR>/<slug>.md` 를 위 형식으로 만든다. `discovered` 와 `summary` 는 반드시 채운다.
- 기존 항목 갱신(merge): 같은 항목이면 해당 상세 파일의 `## Notes` 에 덧붙이거나 본문·`summary` 를 갱신한다. 중복 신규 파일을 만들지 않는다.
- 해결된 항목: frontmatter 를 `status: resolved` + `resolved: {YYYY-MM-DD}` 로 바꾸고, 본문 끝에 짧은 결과를 남긴다. 파일은 지우지 않는다 — 상한(기본 10, `_config.json` 의 `resolved_keep`)을 넘는 오래된 resolved 는 sync 가 정리한다.
- 아이디어: `status: idea` 로 짧은 파일을 만든다. Open 으로 승격할 때는 status 를 바꾸고 본문을 채운다.

**`INDEX.md` 는 직접 쓰지 않는다.** 다음 단계의 sync 가 다시 만든다.

### 4. 동기화

```bash
SF sync -m "followup: <추가·갱신한 슬러그 요약>"
```

- `SYNC=pushed` — 원격까지 올라갔다.
- `SYNC=committed-local` — 커밋은 됐지만 push 를 못 했다 (오프라인·충돌). 괄호 안 사유를 보고한다. 다음 sync 때 다시 push 한다.
- `SYNC=nochange` — 올릴 변경이 없었다.
- `SYNC=failed` — 원격에 닿지 못했다. 괄호 안 사유를 보고한다. 로컬 파일은 그대로 있고 다음 sync 때 다시 올린다.
- `SYNC=local-only` — 동기화가 꺼진 프로젝트다.
- `CONFLICT=` 가 있으면 「스크립트」 절에 적은 대로 사용자에게 알린다.
- `PRUNED=` 가 있으면 상한을 넘어 지운 resolved 슬러그다.

### 5. 양쪽 MEMORY.md 갱신

같은 프로젝트에 대해 **두 위치 모두** 의 `MEMORY.md` 에 `## Followups` 섹션을 넣거나 갱신한다. `<MEMORY_KEY>` 는 `prepare` 출력 값이다.

- `{CLAUDE_MEMORY_PREFIX}/<MEMORY_KEY>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md`
- `{CODEX_MEMORY_PREFIX}/<MEMORY_KEY>{CODEX_MEMORY_SUFFIX}/MEMORY.md`

각 파일에 대해:
1. 파일이 존재하면 읽는다.
2. 이미 `## Followups` 섹션이 있으면 해당 섹션만 교체한다.
3. 없으면 파일 끝에 추가한다.
4. 파일 자체가 없으면 디렉토리 생성 후 새로 만든다.

추가/교체할 섹션 내용 (양쪽 동일):

```markdown
## Followups
- `<INDEX_FILE>` 에 저장소 후속 조치 {N}개 누적 중 (최종 업데이트: {현재 날짜}). 다른 PC 와 동기화된다.
- 새 세션 시작 시 `/followup list` 또는 INDEX.md 를 한 번 훑어 우선순위 판단에 참고하고, 필요한 항목의 상세 파일만 연다. 작업 중 발견된 후속 항목은 `/followup` 으로 추가.
```

`<INDEX_FILE>` 은 `~` 로 시작하는 경로로 적는다 (PC 마다 홈 경로가 달라도 맞도록). `{N}` 은 Open + Pending 합계.

### 6. 완료 보고

사용자에게 알린다:

- `INDEX_FILE` 경로와 `REPO_KEY`
- 추가/갱신된 항목 수 / 전체 Open·Pending 항목 수
- 새로 만든 상세 파일 슬러그 목록
- merge / overwrite / 신규 생성 여부 (+ 마이그레이션을 했으면 그 사실)
- `SYNC` 결과 (push 됐는지, 안 됐으면 이유)
- 양쪽 MEMORY.md 갱신 여부

## list

`/followup list` 이거나 사용자가 남은 followup 을 물으면 기록하지 않고 현황만 보여준다.

```bash
SF prepare
```

`INDEX_FILE` 을 읽어 Open · Decisions Pending 을 제목 + 한 줄 설명으로 보여주고, Ideas 는 개수만 말한다. 항목이 없으면 "이 저장소에 남은 followup 이 없습니다" 라고 한다. 파일을 고치거나 sync 하지 않는다 (마이그레이션이 일어났다면 `prepare` 가 이미 sync 했다).

## 가이드라인

- followup 항목은 **구체적**이고 **검색 가능**해야 한다. "리팩터링 필요" 보다는 "auth middleware: session 만료 처리 누락 — login flow 에서 발견".
- `summary` 는 가볍게 — 한 줄 설명만. 본문은 상세 파일이 책임진다.
- 발견 일자를 반드시 기록 — 시간이 지나면 followup 의 적합성 자체가 흐려진다.
- "다음 세션에서 이어서 작업할 것" 은 followup 이 아니라 `handoff` 이다. 두 스킬을 혼동하지 말 것.
- Resolved 는 짧게 유지 — 항목 archive 가 목적이지 history log 가 아니다.
