---
name: phase-run
description: "페이즈로 나눈 작업을 각 페이즈 경계에서 컨텍스트를 비우고(자기 pane 에 /clear 주입) 새 세션이 HANDOFF.md 를 읽고 다음 페이즈를 이어받도록 자동 전진시키는 스킬. 긴 작업에서 컨텍스트 누적으로 품질이 떨어지는 걸, '페이즈마다 fresh 세션'으로 막는다. 자동 전진은 detached 프로세스가 turn 종료 후 clear+continue 키를 tmux 로 쏴서 무인으로 진행하며, /phase-run pause 한 줄로 멈출 수 있다. 자동 커밋은 절대 하지 않는다. 사용자가 '페이즈 작업', '페이즈로 나눠서', '단계별로 세션 끊어서', '컨텍스트 비우면서 진행', 'phase run', 'phase-run', '페이즈 러너', '단계별 자동 진행', '/phase-run' 등을 말하면 트리거. Usage: /phase-run [continue | pause | resume | stop | status | reset] | <자연어 페이즈 계획>"
user-invocable: true
---

# Phase Run Skill

긴 작업을 **페이즈로 쪼개고**, 각 페이즈가 끝나면 컨텍스트를 비운 뒤(`/clear`) 새 세션이 `HANDOFF.md` 를 읽고 다음 페이즈를 이어받게 하여, **컨텍스트 누적으로 인한 품질 저하를 페이즈 경계마다 리셋**한다.

핵심은 "자기 pane 에 `/clear` + 이어받기 명령을 자동 주입" 하는 것이다. 에이전트는 자기 컨텍스트를 turn 도중에 비울 수 없으므로(=clear 는 툴이 아니라 TUI 명령), turn 이 끝나 idle 이 된 직후 detached 프로세스가 tmux 로 키를 되쏘아 이를 달성한다. 모든 tmux/상태 로직은 `${SKILL_DIR}/scripts/phaseflow.sh` 가 담당한다 — **너(LLM)는 이 스크립트를 호출하고, 각 페이즈의 실제 "작업" 만 직접 수행한다.**

## 불변 원칙 (반드시 지킬 것)

1. **자동 커밋 금지.** `/clear` 는 파일을 건드리지 않으므로 워킹트리는 그대로 다음 세션이 이어받는다. 페이즈 전진을 위해 커밋할 필요가 없다. 커밋은 사용자가 명시적으로 요청할 때만. (`--commit-each` 가 켜진 경우에만, advance 직전에 사용자 확인을 받고 커밋한다.)
2. **`/clear` 는 되돌릴 수 없다.** clear 전에 `HANDOFF.md` 가 다음 페이즈에 필요한 모든 것을 담았는지 **검증**한다. 빠지면 그 컨텍스트는 영구 소실된다. 이게 이 스킬의 생명줄이다.
3. **advance 는 너의 마지막 행동이어야 한다.** `advance` 를 호출하면 detached injector 가 `DELAY` 초 뒤 `/clear` 를 쏜다. advance 이후에는 **추가 툴 호출을 하지 말고**, 짧은 한 줄 보고만 남기고 turn 을 끝내라(그래야 pane 이 idle 이 되어 주입이 깨끗이 안착한다).
4. **페이즈 분해는 시작 시 1회만 사용자 확인.** 그 외 경계마다 차단형 확인은 하지 않는다(무인 전진이 목적). 멈추고 싶으면 사용자가 `/phase-run pause` 를 친다.

## 인자 디스패치

`$ARGUMENTS` 의 첫 토큰으로 분기한다. 모든 스크립트 호출에서 `--pane "$TMUX_PANE"` 와 `--tool {HARNESS_NAME}` 을 넘긴다.

| 첫 토큰 | 동작 |
|---|---|
| (없음) 또는 자연어 계획 | **start** — 계획을 페이즈로 분해 → 사용자 확인 → init → Phase 1 작업 |
| `continue` | **이어받기** — 상태/핸드오프 읽고 현재 페이즈 작업 (주입된 명령이 부르는 경로) |
| `pause` | 자동 전진 일시정지 |
| `resume` | 재개 (현재 페이즈로 clear+continue 재예약) |
| `stop` / `abort` | 중단 (상태 보존) |
| `status` | 진행 상태 표시 |
| `reset` | 상태 파일 삭제 |

`pause` / `resume` / `stop` / `status` / `reset` 은 스크립트를 그대로 호출하고 출력을 사용자에게 전달하면 끝이다:

```bash
bash "${SKILL_DIR}/scripts/phaseflow.sh" <pause|resume|stop|status|reset>
```

---

## START — 새 phase-run 시작

사용자가 자연어로 페이즈 계획(또는 그냥 "이 작업을 페이즈로 나눠서 진행해줘")을 줬을 때.

### 1. 페이즈로 분해

작업을 **컨텍스트 단위로 독립적인** 순서 페이즈로 나눈다. 좋은 페이즈 경계:

- 각 페이즈는 끝나면 다음 페이즈가 이전 대화 로그 없이 `HANDOFF.md` 만으로 이어받을 수 있어야 한다.
- 페이즈 사이 결합도가 낮을수록 좋다(예: 스키마 → 서비스 → API → 테스트).
- 너무 잘게 쪼개면 clear 오버헤드만 늘고, 너무 크면 컨텍스트가 다시 찬다. 보통 2~6개.

### 2. 사용자 확인 (1회)

분해한 페이즈 목록과 각 페이즈의 목표·완료기준을 보여주고 **이대로 진행할지** 확인받는다. 이때 옵션도 함께 확정:

- `--delay <초>`: clear 주입까지 대기(기본 4).
- `--commit-each`: 페이즈마다 커밋(기본 off, 켜면 매 경계에서 커밋 확인을 받음).

여기서의 확인은 "무엇을 할지" 정의이므로 무인 전진 원칙과 충돌하지 않는다.

### 3. init

확정되면 페이즈 제목을 stdin(한 줄당 하나)으로 넘겨 초기화한다:

```bash
bash "${SKILL_DIR}/scripts/phaseflow.sh" init \
  --pane "$TMUX_PANE" --tool {HARNESS_NAME} --delay 4 <<'EOF'
DB 스키마 + 마이그레이션
서비스/리포지토리 구현
API 컨트롤러 + 테스트
EOF
```

이어서 사람이 읽을 풍부한 계획을 `HANDOFF.md` 가 놓일 디렉토리에 `PHASES.md` 로 적어두면 좋다(경로는 아래 `paths` 참고). 각 페이즈의 목표/완료기준/주의사항을 담는다.

> `$TMUX_PANE` 가 비어 있으면(=tmux 밖) 스크립트가 경고하고 자동 전진을 끈다. 이 경우 각 경계에서 사용자가 직접 `/clear` 후 `/phase-run continue` 를 실행해야 한다고 안내한다.

### 4. Phase 1 작업 수행

그 다음 곧바로 **Phase 1 의 실제 작업**을 한다(코드 작성·수정 등). 작업이 끝나면 아래 "페이즈 완료 프로토콜" 로 간다.

---

## CONTINUE — 다음 페이즈 이어받기

`/clear` 직후 주입된 `/phase-run continue` 로 진입하거나, 사용자가 직접 호출했을 때.

### 1. 현재 상태 파악

```bash
bash "${SKILL_DIR}/scripts/phaseflow.sh" current
```

출력의 `CURSOR`/`TOTAL`/`TITLE`/`HANDOFF`/`COMMIT_EACH` 를 읽는다. `STATUS` 가 `done`/`aborted` 면 더 할 일이 없으니 그대로 보고하고 끝낸다.

### 2. 핸드오프 읽기

`HANDOFF=` 가 가리키는 `HANDOFF.md` 를 **반드시 읽는다.** 이게 이전 페이즈가 남긴 유일한 컨텍스트다. 같은 디렉토리의 `PHASES.md`(있으면)도 읽어 전체 계획을 다시 파악한다.

### 3. 현재 페이즈 작업 수행

`TITLE` 페이즈의 실제 작업을 한다. 핸드오프의 `Next Action` 부터 시작한다.

---

## 페이즈 완료 프로토콜 (start/continue 공통, 매 페이즈 끝에)

현재 페이즈의 작업이 끝나면:

### 1. HANDOFF.md 작성 + 완전성 검증

`sessionflow:handoff` 규약을 따라 `HANDOFF.md`(위 `HANDOFF` 경로, = phases/ 의 부모)를 **다음 페이즈 기준으로** 작성한다. 표준 섹션(Context / Last Command / In-Flight Edits / Current State / Next Action / Notes)에 더해 다음을 포함:

```markdown
## Phase Progress
- 완료: Phase {N} — {제목}
- 다음: Phase {N+1} — {제목}
- 상태: `~/.hbrness/sessionflow/<key>/[worktrees/<wt>/]phases/`
- 이어받기: `/phase-run continue`
```

**검증(불변 원칙 2):** clear 전에 스스로 물어라 — "이 핸드오프만 보고, 대화 로그 없이, 다음 페이즈를 시작할 수 있는가?" 빠진 결정·경로·에러·가정이 있으면 지금 채운다. 비밀 값은 절대 적지 않는다.

### 2. (--commit-each 인 경우만) 커밋 확인

`COMMIT_EACH=1` 이면, advance 전에 변경사항을 보여주고 **사용자에게 커밋 확인을 받는다**(불변 원칙 1). 확인받지 못하면 커밋하지 않고 그대로 진행하거나 사용자 지시를 기다린다. `COMMIT_EACH=0` 이면 이 단계는 건너뛴다(커밋하지 않음).

### 3. advance (= 너의 마지막 행동)

```bash
bash "${SKILL_DIR}/scripts/phaseflow.sh" advance --pane "$TMUX_PANE" --tool {HARNESS_NAME}
```

- 더 진행할 페이즈가 있으면: 스크립트가 `DELAY` 초 뒤 자동으로 `/clear` → `/phase-run continue` 를 이 pane 에 주입하도록 예약한다.
- 마지막 페이즈였으면: `✅ 모든 페이즈 완료` 를 출력하고 주입하지 않는다.

### 4. 짧게 보고하고 turn 종료

advance 출력 그대로(자동 전진 예약됨 / 또는 완료 / 또는 tmux 없어 수동 안내)를 **한두 줄로** 사용자에게 전달하고, **추가 작업 없이 turn 을 끝낸다.** 곧 `/clear` 가 들어오므로 길게 쓰지 마라.

tmux 밖이라 자동 전진이 안 되는 경우, advance 출력에 적힌 수동 명령(`/clear` 후 `/phase-run continue`)을 사용자에게 그대로 안내한다.

---

## 디버그 / 경로

```bash
bash "${SKILL_DIR}/scripts/phaseflow.sh" paths   # STATE_DIR, HANDOFF_FILE, pane 도출 확인
```

`HANDOFF_FILE` 의 부모 디렉토리에 `PHASES.md` 를 두면 사람이 전체 계획을 보기 좋다.

## 주의

- **pane 정확도:** 스크립트는 `$TMUX_PANE`(이 프로세스가 사는 pane)을 1순위로 쓴다. `tmux display-message` 는 "사용자가 지금 보고 있는 pane" 을 주므로, 머신에 여러 세션이 떠 있으면 엉뚱한 세션을 clear 할 수 있어 쓰지 않는다. 그래서 `advance`/`init` 에 항상 `--pane "$TMUX_PANE"` 를 넘겨라.
- **Codex:** 기본 clear 명령은 `/new`, 제출은 CSI-u Enter 다. 사용 중인 Codex 버전의 새 대화 명령이 다르면 `init --clear-cmd '<명령>'` 으로 지정하라.
- **무한 루프 방지:** cursor 가 total 을 넘으면 자동으로 종료하며, 안전 상한(`PHASEFLOW_MAX_PHASES`, 기본 50)이 있다.
- **멈춤:** 자동 전진이 폭주하거나 개입이 필요하면 사용자는 `/phase-run pause` 한 줄로 멈추고, 점검 후 `/phase-run resume` 으로 재개한다.
