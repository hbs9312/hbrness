---
name: handoff
description: "현재 워크트리/세션의 in-flight 컨텍스트(편집 중인 파일·마지막 실행 명령·실패한 에러·즉시 다음 한 줄)를 저장소 + 브랜치 단위 핸드오프 파일로 직렬화하고, private state repo 로 여러 PC 사이에 동기화한다. followup(저장소 단위 후속 조치)과 달리 '지금 작업을 다음 세션이 그대로 이어받는 것' 이 목적이며, 브랜치별로 파일이 분리된다. 다른 PC 에서 같은 브랜치를 체크아웃하면 그 핸드오프를 불러올 수 있다(load). 사용자가 'handoff', 'hand off', '인계', '세션 끊김 대비', '이어서 작업', '컨텍스트 저장', 'save session context', 'prepare for next session', 'write HANDOFF.md', '핸드오프', 'handoff 남겨줘', '/handoff' 등을 말하면 트리거. '핸드오프 불러와', '핸드오프 이어받기', '다른 PC 에서 하던 거 이어서', 'handoff load' 처럼 불러오기를 요청하면 load 로 동작. Usage: /handoff [load | -m | -o] [메시지]"
model: sonnet
---

# Handoff Skill

현재 세션의 **in-flight 컨텍스트** — 편집 중인 파일·마지막 실행 명령·실패한 에러·즉시 다음 한 줄 — 을 핸드오프 파일에 기록하여, 다음 세션(Claude/Codex/Grok/Devin 어느 쪽이든, **어느 PC 든**)이 작업을 **그 자리에서 그대로** 이어받을 수 있게 한다.

핸드오프는 **저장소 + 브랜치** 로 찾는다. 저장소는 경로가 아니라 origin remote URL 로 가리고, 파일은 브랜치마다 하나다. 그래서 회사 PC 의 워크트리에서 남긴 핸드오프를 집 PC 에서 같은 브랜치를 체크아웃해 바로 이어받을 수 있다. git 은 한 브랜치를 두 워크트리에 동시에 체크아웃하지 못하게 막으니, 한 PC 안에서 워크트리끼리 덮어쓸 일도 없다.

`followup` 과의 차이:

| | `handoff` | `followup` |
|---|---|---|
| 범위 | 저장소 + 브랜치 단위 (1회성·in-flight) | 저장소 단위 (영속·누적) |
| 목적 | "지금 작업을 다음 세션이 그대로 이어받게" | "나중에 처리해야 할 일" 백로그 |
| 내용 | 마지막 명령·에러·편집중 파일·다음 한 줄 | TODO·결정 보류·발견된 이슈·아이디어 |
| 저장 | `handoffs/<branch>.md` | `followups/<slug>.md` (+ 생성되는 `INDEX.md`) |
| 수명 | 다음 세션에서 이어받으면 보통 삭제 | 항목별로 Resolved 처리하며 누적 |

> `phase-run` / `phase-loop` / `relay` 가 페이즈 경계에서 쓰는 `HANDOFF.md` 는 이 스킬의 파일과 **다르다.** 그쪽은 tmux pane 에 묶인 PC 로컬 오케스트레이션 상태라 `~/.hbrness/sessionflow/<경로키>/` 에 그대로 있고 동기화하지 않는다. 형식(섹션 구성)만 이 스킬 규약을 따른다.

## 스크립트

경로 계산·pull·push 는 전부 `sfstate.py` 가 한다. 이 문서에서 `SF` 는 다음 명령을 뜻한다:

```bash
python3 "${SKILL_DIR}/../../scripts/sfstate.py"
```

- `SF prepare` — state repo 를 원격과 맞추고(pull), 예전 경로 기준 데이터가 있으면 옮긴 뒤 경로를 `KEY=VALUE` 로 출력한다.
- `SF sync -m "<메시지>"` — 이 저장소의 변경만 commit 해서 push 한다.
- `SF status` — 이 저장소의 핸드오프(현재 브랜치 + 다른 브랜치)·followup 현황을 짧게 보여준다.

`prepare` 출력에서 쓰는 값:

| 키 | 뜻 |
|---|---|
| `HANDOFF_FILE` | 현재 브랜치의 핸드오프 파일 |
| `HANDOFFS_DIR` | 이 저장소의 핸드오프 디렉토리 (브랜치 이름의 `/` 는 하위 디렉토리가 된다) |
| `BRANCH` | 현재 브랜치. detached HEAD 면 `_detached/<sha>`, git 이 아니면 비어 있고 파일은 `_nogit.md` |
| `REPO_KEY` | 저장소 키 (예: `github.com/hbs9312/hbrness`). 비면 remote 가 없는 프로젝트 |
| `SYNC` | `on` 이면 push 까지 된다. `off` 면 이 PC 에만 저장 (`SYNC_NOTE` 에 이유) |
| `MEMORY_KEY` | MEMORY.md 경로에 쓰는 키 |

`SYNC=off` 여도 기록은 된다. 사용자에게 `SYNC_NOTE` 를 한 줄로 알리기만 하고 계속한다.

## 인자

`$ARGUMENTS` 또는 사용자 요청에서 파싱한다.

- `load`: 기록하지 않고 핸드오프를 불러온다 (아래 "load" 절).
- `-m`: 기존 핸드오프가 있으면 확인 없이 **merge** (이전 컨텍스트 + 이번 세션).
- `-o`: 기존 핸드오프가 있으면 확인 없이 **overwrite** (이번 세션만).
- 그 외 텍스트: 사용자가 함께 전달한 **추가 컨텍스트** — 핸드오프에 반영한다.

기본 동작: 기존 파일이 있으면 사용자에게 차이를 보여주고 **merge / overwrite / cancel** 중 선택을 받는다 (handoff 는 followup 과 달리 자동 merge 가 위험할 수 있음 — 이전 in-flight 상태가 이미 무효일 수 있기 때문).

## 저장 경로

```text
~/.hbrness/state/                       # private state repo 의 clone (PC 마다 하나)
└── <host>/<owner>/<repo>/              # REPO_KEY
    ├── handoffs/
    │   ├── main.md
    │   └── feat/login.md               # 브랜치 feat/login
    └── followups/                      # followup 스킬 영역 — 이 스킬은 건드리지 않는다
```

remote 가 없는 프로젝트는 `~/.hbrness/state/_local/<경로키>/handoffs/` 에 저장되고 동기화되지 않는다.

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

비밀 값(env 파일·토큰·자격증명 등)은 절대 기록하지 않는다. state repo 는 원격에 push 된다.

**다른 PC 에서 읽힌다는 점을 염두에 둔다.** 커밋·push 하지 않은 변경은 다른 PC 에 없다. `Current State` 에 "미커밋 변경 N개 — 이 PC(`{hostname}`)에만 있음" 처럼 적어, 다른 PC 에서 이어받는 세션이 그 사실을 알게 한다.

### 2. 준비 + 기존 파일 처리

```bash
SF prepare
```

- `MIGRATE=migrated` 가 보이면 이 PC 의 예전 경로 기준 핸드오프·followup 을 저장소 기준으로 옮긴 것이다. 보고에 한 줄로 넣는다.
- `PULL=failed` 면 로컬 사본으로 계속하고 보고에 남긴다.

`HANDOFF_FILE` 이 이미 있으면:

1. 읽는다.
2. 여전히 유효한 이전 컨텍스트(예: 같은 작업을 이어가는 중)인지, 무효(다른 작업으로 전환)인지 식별.
3. `-m` → merge, `-o` → overwrite 로 즉시 진행.
4. 플래그가 없으면 사용자에게 차이를 요약해서 보여주고 **merge / overwrite / cancel** 중 선택하게 한다.

기존 파일이 없으면 그냥 진행.

### 3. 핸드오프 작성

저장 디렉토리가 없으면 만든다 (브랜치에 `/` 가 있으면 하위 디렉토리까지):

```bash
mkdir -p "$(dirname "<HANDOFF_FILE>")"
```

빈 섹션은 생략하고 다음 구조로 간결하게 작성한다:

```markdown
# Session Handoff

> Generated: {현재 날짜·시간}
> Repo: {REPO_KEY 또는 project_root}
> Branch: {활성 브랜치}
> Host: {hostname} · Working Directory: {현재 PC 의 project_root}
> Worktree: {wt_name 또는 "main"}

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

{git status 요약: 브랜치, staged/unstaged/untracked, 원격과의 차이(ahead/behind). 미커밋 변경은 이 PC 에만 있다고 적는다. 빌드/테스트 상태가 있으면 함께.}

## Next Action

{다음 세션이 즉시 실행해야 할 단 한 가지. 명령과 함께 적는다.}

```
{재현 명령}
```

## Notes

{환경 변수·실행 중인 프로세스·임시 가정. 다음 세션이 모르면 막힐 만한 것만.}
```

파일 경로는 저장소 루트 기준 상대 경로로 적는다 — 다른 PC 는 clone 위치가 다르다.

`Next Action` 은 가능한 한 **하나** 만 적는다. 여러 개 떠올랐다면 가장 즉시 필요한 것 하나만 여기에 두고, 나머지는 followup 으로 이관하라고 보고에 언급한다.

### 4. 동기화

```bash
SF sync -m "handoff: <BRANCH>"
```

- `SYNC=pushed` — 원격까지 올라갔다.
- `SYNC=committed-local` — 커밋은 됐지만 push 를 못 했다 (오프라인·충돌). 괄호 안 사유를 보고한다. 다음 sync 때 다시 push 한다.
- `SYNC=local-only` — 동기화가 꺼진 프로젝트다.

### 5. 양쪽 MEMORY.md 갱신

같은 프로젝트에 대해 **두 위치 모두** 의 `MEMORY.md` 에 `## Handoff` 섹션을 넣거나 갱신한다. `<MEMORY_KEY>` 는 `prepare` 출력 값이다.

- `{CLAUDE_MEMORY_PREFIX}/<MEMORY_KEY>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md`
- `{CODEX_MEMORY_PREFIX}/<MEMORY_KEY>{CODEX_MEMORY_SUFFIX}/MEMORY.md`

각 파일에 대해:
1. 파일이 존재하면 읽는다.
2. 이미 `## Handoff` 섹션이 있으면 다음 규칙으로 병합:
   - 같은 브랜치의 핸드오프 라인이 이미 있으면 갱신.
   - 다른 브랜치의 핸드오프 라인은 그대로 보존.
   - 예전 형식(`worktrees/<wt-name>` 이나 `~/.hbrness/sessionflow/...` 경로)의 라인은, 같은 작업을 가리키면 새 라인으로 바꾼다.
3. 섹션이 없으면 파일 끝에 추가.
4. 파일 자체가 없으면 디렉토리 생성 후 새로 만든다.

추가/교체할 섹션 내용 (양쪽 동일):

```markdown
## Handoff
활성 세션 핸드오프 (저장소 기준, 다른 PC 와 동기화):
- {BRANCH}: `<HANDOFF_FILE>` (최종 업데이트: {현재 날짜})
새 세션 시작 시 현재 브랜치와 일치하는 핸드오프를 읽어 작업을 이어간다. 목록에 없으면 `/handoff load` 로 다른 PC 에서 남긴 핸드오프를 확인한다.
```

`<HANDOFF_FILE>` 은 `~` 로 시작하는 경로로 적는다 (PC 마다 홈 경로가 달라도 맞도록). 활성 핸드오프가 여러 브랜치에 걸쳐 있을 수 있으므로 라인을 **추가** 하는 식으로 관리한다.

### 6. 완료 보고

사용자에게 알린다:

- 핸드오프 파일 경로 (`REPO_KEY` + `BRANCH`)
- 새로 만들어졌는지 / merge 됐는지 / overwrite 됐는지
- 캡처한 Next Action 한 줄 요약
- `SYNC` 결과 (push 됐는지, 안 됐으면 이유)
- 양쪽 MEMORY.md 갱신 여부
- (있다면) followup 으로 옮기는 게 더 맞을 항목들에 대한 제안

## load

`/handoff load` 이거나 사용자가 다른 PC·이전 세션의 핸드오프를 이어받으려 할 때. 기록하지 않는다.

```bash
SF prepare
SF status --no-pull
```

1. `HANDOFF_FILE` 이 있으면 읽고, 그 내용으로 작업을 이어갈 준비를 한다:
   - `Branch` 가 현재 브랜치와 같은지 확인한다.
   - `Host` 가 이 PC 가 아니고 `Current State` 에 미커밋 변경이 있다고 적혀 있으면, 그 변경은 이 PC 에 없다고 사용자에게 먼저 알린다.
   - `git fetch` 후 원격 브랜치가 앞서 있으면 pull 이 필요하다고 알린다 (직접 pull 하지는 않는다).
   - Next Action 을 한 줄로 보여주고 진행할지 묻는다.
2. 현재 브랜치 핸드오프가 없으면 `status` 의 "다른 브랜치 핸드오프" 목록을 보여주고, 어느 브랜치를 체크아웃해 이어갈지 묻는다. 체크아웃은 사용자가 고른 뒤에만 한다.
3. 위 "5. 양쪽 MEMORY.md 갱신" 과 같은 규칙으로 이 PC 의 MEMORY.md 에 `## Handoff` 라인을 넣는다 (다음 세션부터 바로 보이게).

## 가이드라인

- 새 세션이 전체 대화 로그를 다시 읽지 않고도 **그 자리에서** 작업을 재개할 수 있도록 구체적으로.
- 모호한 표현 대신 파일:줄, 명령 원문, 에러 메시지 원문을 사용.
- "다음 작업 후보 N개" 처럼 백로그 성격이면 followup 스킬 사용을 권하라.
- 다른 브랜치의 핸드오프는 건드리지 말 것.
- 비밀 값은 절대 포함하지 말 것.
