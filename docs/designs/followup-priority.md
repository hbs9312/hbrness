# followup 우선순위 (P0~P3) — 구현 계획

- 상태: 구현 (sessionflow 1.8.0 · sessionflow-status mod 0.8.0, 2026-10-16)
- 브랜치: `feat/followup-priority` (워크트리 `../hbrness-followup-priority`)
- 작성: 2026-10-16
- 범위: hbrness sessionflow (sfstate·followup 스킬·문서·테스트) + claude-config 의 `sessionflow-status` mod

## 정한 것 (사용자 결정)

1. 우선순위는 **P0~P3** 네 단계다. P0 가 가장 급하다.
2. **기존 항목은 모두 같은 우선순위**로 둔다 — frontmatter 에 `priority` 가 없으면 기본값으로 본다. 파일은 고치지 않는다(다시 올릴 것도, 다른 PC 와 어긋날 것도 없다).
3. 정렬: 같은 status 안에서 **우선순위(P0→P3) → 같은 우선순위는 추가된 날짜(`discovered`) 순 → 같은 날짜는 제목 순**.
4. mod 까지 같이 바꾼다.

## 구현 전에 확인한 것 (2026-10-16 사용자 확인 — 제안대로)

- **기본값**: P2 로 둔다(아래 단계 정의에서 "보통"). P3 가 맞으면 상수 하나만 바꾼다.
- **날짜 방향**: "추가된 날짜 순"을 **먼저 추가된 것부터(오름차순)** 로 읽었다. 지금 INDEX 는 최신부터(내림차순)라 순서가 뒤집힌다. 최신부터가 맞으면 정렬 키 방향만 바꾼다.
- **어느 status 에 적용하나**: open·pending·idea 에 적용한다. resolved 는 지금처럼 해결 날짜 최신부터(우선순위는 의미가 없다).

## 데이터 형식

항목 파일 frontmatter 에 한 줄을 더한다.

```yaml
priority: P1    # P0 | P1 | P2 | P3, 없으면 P2
```

단계 정의(스킬·INDEX 머리말에 같은 문구를 쓴다):

| 단계 | 뜻 |
|---|---|
| P0 | 지금 막혀 있거나 바로 해야 한다 |
| P1 | 곧 (이번 작업 흐름 안에서) |
| P2 | 보통 — 기본값 |
| P3 | 언젠가 / 우선순위 낮음 |

읽을 때 대소문자는 가리지 않는다(`p1` → `P1`). P0~P3 가 아니면 기본값으로 본다(항목은 버리지 않는다).

## 변경 — hbrness (sessionflow 1.7.2 → 1.8.0)

### 1. `plugins/sessionflow/scripts/sfstate.py`

- 상수: `PRIORITIES = ("P0", "P1", "P2", "P3")`, `DEFAULT_PRIORITY = "P2"`, `priority_of(value) -> str`(정규화).
- `load_items` (현재 381행): 항목에 `"priority"` 를 더한다.
- `group_items` (현재 419–424행): open·pending·idea 의 정렬 키를 `(PRIORITIES.index(p), discovered, title)` 오름차순으로 바꾼다. 지금은 `(discovered, title)` 내림차순이다. resolved 는 그대로.
  - `discovered` 가 비어 있는 항목은 같은 우선순위 안에서 맨 뒤로 보낸다(빈 문자열이 오름차순 맨 앞에 오지 않게).
- `build_index` (현재 428행~):
  - Open / Decisions Pending 표 맨 앞에 `우선` 칸을 둔다: `| 우선 | 제목 | 한 줄 설명 | Discovered | 상세 |`.
  - Ideas 줄 앞에 `[P1]` 처럼 붙인다.
  - 머리말 개수 줄에 P0·P1 개수를 덧붙인다: `> Open: 3 (P0 1 · P1 1) · …` — 열지 않고도 급한 것이 있는지 보이게.
- `cmd_index --json` (현재 809–815행): `fields` 에 `"priority"` 를 더한다(mod 가 쓴다).
- 새 서브커맨드 `set-priority --dir D <slug> <P0|P1|P2|P3>`: 항목 파일의 frontmatter `priority` 를 `fm_set`(현재 352행)으로 넣거나 바꾸고 INDEX 를 다시 만든다. 동기화는 하지 않는다(호출한 쪽이 `sync`). 없는 slug·잘못된 값은 exit 1. 스킬과 mod 칩이 frontmatter 를 손으로 고치지 않고 이걸 부르게 해서 형식이 흔들리지 않게 한다.
- `status` 출력의 followups 줄에 P0 개수를 붙인다(있을 때만).
- 레거시 INDEX 파서(`parse_legacy_index`)와 마이그레이션은 건드리지 않는다 — 옮긴 항목은 priority 가 없으니 기본값이 된다.

### 2. followup 스킬 (`plugins/sessionflow/skills/followup/SKILL.common.md`)

- 항목 형식(현재 85–87행)에 `priority: P2` 줄과 단계 정의를 더한다.
- 신규 항목: 사용자가 말한 우선순위를 쓰고, 없으면 P2. 인자 `-p P0|P1|P2|P3` 를 받는다(Usage 줄도).
- 우선순위 변경 요청("이거 P0 으로", "우선순위 낮춰")은 `set-priority` 를 부른 뒤 `sync` 한다.
- INDEX 를 훑을 때 `우선` 칸을 먼저 본다는 안내를 넣는다.
- 같은 SKILL.common.md 로 Claude·Codex·Grok·Devin 빌드가 나오므로 네 도구가 같이 바뀐다.

### 3. 테스트 (`tests/test_sfstate.py`)

- 정렬: 우선순위 → 날짜 오름차순 → 제목, discovered 없는 항목은 그 우선순위 맨 뒤.
- 필드가 없거나 잘못된 값이면 P2, 소문자 `p0` 는 P0.
- INDEX 표의 `우선` 칸, Ideas 의 `[Pn]`, 머리말 P0·P1 개수.
- `index --json` 에 priority.
- `set-priority`: 넣기·바꾸기·없는 slug·잘못된 값, frontmatter 의 다른 줄은 그대로.
- 기존 IndexTests 의 순서 기대값은 새 정렬에 맞게 고친다.

### 4. 문서

- `plugins/sessionflow/README.md` — followup 항목 형식과 INDEX 설명.
- `docs/USAGE_FLOW.md` · `docs/USAGE_FLOW_AGENT.md` — 둘을 같이(`/followup -p P1 …`, 우선순위 변경).

### 5. 커밋·버전

feat 커밋 → `chore(sessionflow): bump 1.7.2 → 1.8.0`. 하던 대로 xreview(codex) 2라운드 뒤 커밋한다. 이 레포는 main 에 직접 쌓는 규칙이라, 끝나면 이 브랜치를 main 으로 fast-forward 하고 push 한다.

## 변경 — claude-config 의 `sessionflow-status` mod

`~/.claude/mods/sessionflow-status` (저장소 `hbs9312/claude-config`). hbrness 1.8.0 이 먼저 나가야 priority 가 들어온다. 그 전의 sfstate 와 만나도 priority 가 없어 P2 로 보일 뿐 깨지지 않는다.

- `types/index.d.ts`: `FollowupItem` 에 `priority?: 'P0' | 'P1' | 'P2' | 'P3'`.
- `hooks/register.tsx`
  - `parseIndex` (현재 109행): priority 가 없으면 `'P2'`.
  - 목록 (현재 572행~): 항목 앞에 우선순위 표시 — P0 은 error 색, P1 은 warning 색, P2·P3 는 흐리게. **순서는 `index --json` 이 준 그대로 쓴다** — 정렬은 sfstate 한 곳에서만 한다.
  - 프롬프트 위 요약 줄 (FOLLOWUP 버튼, 현재 543행 근처): open 에 P0 가 있으면 `FOLLOWUP 3 · P0 1` 처럼 보인다.
  - 항목 화면 (현재 503행~): 우선순위를 보여 주고, 칩 버튼 **우선순위**(hotkey `p`)를 더한다. 칩 `[⇅ 우선순위 · <slug>]` 의 `chipContext` 는 "사용자가 칩 옆에 적은 P0~P3 로 `sfstate.py set-priority` 를 부르고 `sync` 한다. 적은 게 없으면 물어본다"를 시킨다. `ACTIONS`·`ASKS` (현재 32–55행)에 항목을 더한다.
- `tests/sessionflow-status.test.tsx`: parseIndex 기본값, 표시 색, 요약 줄 P0 개수, 우선순위 칩 라벨·컨텍스트.
- `.claude-plugin/plugin.json` version 을 올린다(minor).

## 진행 순서

1. hbrness: sfstate + 테스트 → 스킬·문서 → xreview 2라운드 → feat + bump 커밋 → main 으로 fast-forward·push → `bash scripts/build.sh all` → `node bin/hbrness.js install claude|codex|grok|devin sessionflow`.
2. claude-config: mod 변경 + 테스트 → 커밋·push.
3. 다른 PC: `git pull`(hbrness·claude-config) → install.

## 동기화 영향

- priority 가 없는 기존 파일은 그대로라 다시 올라가지 않는다.
- 우선순위를 바꾸면 그 항목 파일만 바뀌어 sync 가 올린다. 두 PC 가 같은 항목을 동시에 바꾸면 지금처럼 원격본을 받고 이 PC 버전은 `_conflicts/` 로 비켜 둔다.
- INDEX.md 는 생성물이라 올리지 않으니 정렬·표 형식이 바뀌어도 원격에는 영향이 없다.
