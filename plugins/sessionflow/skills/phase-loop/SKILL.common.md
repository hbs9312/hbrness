---
name: phase-loop
description: "구현 → 다른 에이전트 코드리뷰(xreview) → 커밋 → push → PR → 핸드오프 → 컨텍스트 비우고 새 세션 으로 다음 페이즈를 이어받는 흐름을, 모든 페이즈(=PR 단위)가 끝날 때까지 자동 반복하는 루프 스킬. phase-run 의 페이즈 경계 컨텍스트 리셋 엔진 위에, 각 경계마다 리뷰·출하(commit/push/PR)를 끼워 넣은 상위 워크플로우. 개인 레포는 브랜치에 직접, 팀 레포는 워크트리+스택 PR 로 진행한다. 자동화 수준은 모드별(팀=무인, 개인=커밋 전 확인)이고 /phase-loop pause 로 멈춘다. 사용자가 '루프 스킬', '구현 루프', '자동 루프', '페이즈 루프', '구현부터 PR까지 자동', '리뷰하고 커밋하고 PR까지 반복', 'phase loop', 'phase-loop', '/phase-loop' 등을 말하면 트리거. Usage: /phase-loop [continue | pause | resume | stop | status | reset] | <자연어 구현 계획>"
user-invocable: true
argument-hint: "[continue|pause|resume|stop|status|reset] | <구현 계획>"
---

# Phase Loop Skill

긴 구현 작업을 **페이즈(= PR 단위)로 쪼개고**, 각 페이즈마다 다음을 자동으로 돈다:

```
(이미 이번 페이즈 브랜치 위) 구현 → xreview(다른 에이전트) N라운드 → 커밋 → push → PR
     → [팀 모드] 다음 페이즈 stacked 브랜치 cut(다음 세션이 깨어날 자리) → 핸드오프
     → /clear 로 컨텍스트 비우고 새 세션이 '이미 다음 PR 브랜치 위'에서 이어받기 → … 모든 페이즈 끝까지 반복
```

`sessionflow:phase-run` 의 "페이즈 경계마다 컨텍스트를 리셋한다" 엔진을 그대로 재사용하고, 그 경계에 **리뷰·출하(commit/push/PR)** 를 끼워 넣은 상위 워크플로우다. 상태머신·tmux 주입은 phase-run 의 `phaseflow.sh` 가 담당하고(별도 네임스페이스 `phase-loop`), **너(LLM)는 `${SKILL_DIR}/scripts/loop.sh` 를 호출하면서 각 페이즈의 실제 작업(구현·리뷰 반영·커밋·PR·핸드오프)만 직접 수행한다.**

## 불변 원칙 (반드시 지킬 것)

1. **커밋 정책은 모드별.**
   - **팀 모드**(워크트리+브랜치+PR): main 을 건드리지 않고 PR 이 리뷰 게이트이므로 commit→push→PR→advance 를 **무인**으로 진행한다.
   - **개인 모드**(브랜치/메인 직접): 커밋 **직전 사용자 확인**을 받는다. 확인 전엔 커밋하지 않는다.
   - `--auto` 면 개인 모드도 무인, `--confirm` 이면 팀 모드도 매 커밋 확인. 정책은 `PHASES.md` 의 `Commit policy` 에 박혀 모든 fresh 세션이 동일하게 따른다.
2. **`/clear` 는 되돌릴 수 없다.** advance 직전 `HANDOFF.md` 가 다음 페이즈에 필요한 모든 것(스택 상태·다음 분기 base·다음 액션)을 담았는지 **검증**한다. 빠지면 그 컨텍스트는 영구 소실된다.
3. **advance 는 너의 마지막 행동이어야 한다.** advance 호출 후엔 추가 툴 호출 없이 짧게 보고하고 turn 을 끝내라(곧 `/clear` 가 들어온다).
4. **xreview 는 비동기다.** 리뷰를 start 한 뒤엔 turn 을 끝내고 **완료 핑을 기다린다.** 핑이 오면(이 SKILL 지침이 컨텍스트에 남은 상태에서) 결과를 읽고 라운드를 잇거나 다음 단계로 간다.
5. **계획 분해·모드는 시작 시 1회만 확인.** 그 외 경계마다 차단형 확인은 없다(개인 모드 커밋 확인 제외). 멈추려면 사용자가 `/phase-loop pause`.
6. **자동 커밋의 범위는 "이번 페이즈 변경분"으로 한정.** 의도치 않은 파일을 끌어들이지 않는다. push 는 remote 가 있을 때만, PR 은 팀 모드(또는 명시)일 때만.
7. **다음 페이즈 브랜치는 "완료 프로토콜"에서 미리 cut 한다(팀 모드).** 이번 페이즈를 commit→push→PR 한 뒤, advance 직전에 다음 페이즈의 stacked 브랜치를 잘라 **워킹트리를 그 위로 옮긴다.** 그래야 `/clear` 후 fresh 세션이 **이미 자기 PR 브랜치 위**에서 깨어난다(= 각 페이즈가 독립된 PR 로 확정). 첫 페이즈 브랜치는 워크트리 생성 시 이미 잘려 있고, 마지막 페이즈·개인 모드는 이 단계가 없다.

## 인자 디스패치

`$ARGUMENTS` 의 첫 토큰으로 분기한다. 모든 phaseflow 호출은 `loop.sh pf …` 로 감싸 `phase-loop` 네임스페이스를 쓴다.

| 첫 토큰 | 동작 |
|---|---|
| (없음) 또는 자연어 계획 | **START** — 상태/스테이징 점검 후: 진행중이면 안내, 스테이징된 계획 있으면 채택, 없으면 새 계획 수립 |
| `continue` | **이어받기** — 현재 페이즈 작업 (주입된 `/clear` 후 자동 진입 경로) |
| `pause` / `resume` / `stop` / `status` / `reset` | phaseflow 제어를 그대로 위임 |

제어 커맨드는 위임하고 출력만 전달한다:

```bash
bash "${SKILL_DIR}/scripts/loop.sh" pf <pause|resume|stop|status|reset>
```

> **xreview 완료 핑**(`[xreview:live] 리뷰 완료 …`)은 `/phase-loop` 호출이 아니라 일반 user 메시지로 들어온다. 페이즈 진행 중(=clear 전)이라 이 SKILL 지침이 컨텍스트에 남아 있으니, 핑을 받으면 아래 "xreview 라운드" 절차를 그대로 잇는다.

---

## START — 새 루프 시작 / 스테이징된 계획 채택

먼저 현재 상태를 점검한다:

```bash
bash "${SKILL_DIR}/scripts/loop.sh" paths
bash "${SKILL_DIR}/scripts/loop.sh" pf status
```

- **이미 진행 중**(status 가 active/paused) → 새로 시작하지 말고 `continue`/`status` 를 안내한다(상태 덮어쓰기 방지).
- **진행 중 아님 + `PHASES_FILE` 존재 + 그 안에 phase-loop 설정 헤더 있음** → 팀 부트스트랩으로 미리 스테이징된 계획이다. → 아래 **"채택"** 으로 간다.
- **진행 중 아님 + 스테이징 없음** → 아래 **"새 계획 수립"** 으로 간다.

### 새 계획 수립

#### 1. 모드 추정 → 확인

```bash
bash "${SKILL_DIR}/scripts/loop.sh" detect-mode
```

추정 결과(personal/team + 이유)를 보여주고 **사용자에게 확정**받는다(휴리스틱은 틀릴 수 있다 — 예: 협업 레포여도 개인 작업일 수 있음). 동시에 옵션도 확정:

- 커밋 정책: 팀=auto / 개인=confirm 기본, `--auto`/`--confirm` 으로 override.
- (팀) 스택 정책: 페이즈들이 **서로 의존적이면 stack**(PR base=직전 브랜치), **독립적이면 parallel**(PR base=통합 base). 점진 구현은 대개 stack.
- (팀) 통합 base(예: `origin/main`)·slug·브랜치 명명규칙(예: `<slug>/NN`).
- xreview: reviewer(생략=반대편 도구), **페이즈당 최대 라운드 N**(기본 2 — blocking 없거나 approve 면 N 전 조기종료), scope=working. 페이즈마다 이 N 라운드를 돈다.

#### 2. 페이즈로 분해 → 1회 확인

작업을 **컨텍스트 단위로 독립적인** 순서 페이즈로 나눈다(보통 2~6개). 좋은 경계:
- 각 페이즈는 끝나면 다음 페이즈가 대화 로그 없이 `HANDOFF.md`+`PHASES.md` 만으로 이어받을 수 있어야 한다.
- **페이즈 = PR 단위.** 하나의 PR 로 리뷰·머지하기 적당한 응집된 변경이어야 한다.
- 각 페이즈의 **목표·완료기준**을 명시(컨텍스트 없는 fresh 세션이 모호함 없이 실행할 수 있을 만큼).

분해 결과를 보여주고 **이대로 진행할지 확인**받는다(불변 원칙 5).

#### 3. init 전 체크리스트 (pf init 직전 게이트)

`pf init` 은 가볍다(페이즈 제목 + pane + 옵션만 받아 `state.env`/`phases.tsv` 작성). 하지만 init 은 **clear-and-resume 루프로 들어가는 관문**이라, `/clear` 후 fresh 세션이 대화 로그 없이 이어받을 수 있게 컨텍스트가 **디스크에 박혀 있어야** 한다. 아래를 모두 확인한 뒤에만 init 으로 간다(개인 모드 step 4, 팀 모드는 "채택"의 pf init):

- [ ] **tmux pane** — `$TMUX_PANE` 존재. 없으면 자동 전진 불가(init 이 경고 + 경계마다 수동 `/clear`+continue). 사용자에게 그 사실을 알린다.
- [ ] **PHASES.md 작성됨** — `loop.sh paths` 의 `PHASES_FILE` 경로에. 헤더(Mode/Commit policy/Stack/Integration base/Branch scheme/xreview) + **각 페이즈의 목표·완료기준·(팀)브랜치·PR base**. clear 후 fresh 세션의 **유일한 설정 진실원**이다.
- [ ] **원본 근거 참조 가능** — 분해의 바탕이 된 스펙/PRD/이슈/계획을 **안정적 경로·URL·이슈번호로 PHASES.md 에서 참조**. 대화에만 있는 컨텍스트는 clear 후 소실된다.
- [ ] **워킹트리 상태 known** — init 은 파일을 건드리지 않고 워킹트리가 그대로 다음 세션으로 넘어간다. clean(또는 의도된 staged) 상태인지 확인.
- [ ] **결정 4종 확정·기록** — mode / commit 정책 / stack·parallel / 통합 base·slug·브랜치 규칙·xreview N. 전부 PHASES.md 헤더에.
- [ ] **(팀) 부트스트랩 준비** — 워크트리 + 첫 브랜치 + remote 존재, 그리고 pf init 은 **워크트리 cwd 에서** 돈다(메인에서 돌리면 네임스페이스 어긋남).
- [ ] **(xreview) 반대편 CLI**(claude/codex)가 PATH + tmux 안. **(push/PR) remote + `gh` 인증**(+ 있으면 PR 템플릿).
- [ ] **비밀값 없음** — PHASES.md/HANDOFF.md 어디에도 토큰·자격증명·PII 금지.

빠진 게 있으면 init 하지 말고 먼저 채운다(특히 PHASES.md — 이게 없으면 clear 후 루프가 깨진다).

#### 4. 분기 — 개인 / 팀

**개인 모드:**
1. `PHASES.md` 를 `loop.sh paths` 의 `PHASES_FILE` 경로에 작성(아래 포맷).
2. phaseflow init:
   ```bash
   bash "${SKILL_DIR}/scripts/loop.sh" pf init \
     --pane "$TMUX_PANE" --tool {HARNESS_NAME} \
     --continue-prompt "/phase-loop continue" --delay 4 <<'EOF'
   <Phase 1 제목>
   <Phase 2 제목>
   …
   EOF
   ```
3. 곧바로 **Phase 1 작업**(아래 "페이즈 프로토콜")로 간다.

**팀 모드:** 워크트리를 만들고 거기서 루프가 돌아야 한다(phaseflow 는 같은 pane/cwd 를 재사용하므로 메인 체크아웃에선 워크트리로 못 옮긴다). 그래서 **수동 부트스트랩**:
1. 워크트리 + 첫 페이즈 브랜치 생성:
   ```bash
   bash "${SKILL_DIR}/scripts/loop.sh" worktree-create \
     --slug <slug> --base <통합base> [--first-branch <slug>/01-…]
   ```
   출력의 `WORKTREE`·`FIRST_BRANCH`·`PHASES_FILE`(그 워크트리의 네임스페이스) 를 받는다.
2. `PHASES.md` 를 출력된 `PHASES_FILE` 경로(=워크트리 네임스페이스)에 작성한다. **여기서 phaseflow init 은 하지 않는다**(cwd 가 메인이라 네임스페이스가 어긋난다 — init 은 워크트리 세션이 한다).
3. 사용자에게 **부트스트랩 안내**를 출력하고 **여기서 멈춘다**:
   ```
   팀 모드 워크트리 생성됨: <WORKTREE>
   다음을 실행해 그 워크트리에서 루프를 시작하세요:
     cd <WORKTREE> && {HARNESS_NAME}
   새 세션에서:
     /phase-loop start
   ```

### 채택 — 스테이징된 계획으로 init (팀 부트스트랩 재진입)

워크트리 세션에서 `/phase-loop start` 로 들어와, `PHASES_FILE` 에 phase-loop 설정 헤더가 이미 있을 때:
1. `PHASES.md` 를 읽어 모드·정책·페이즈 목록을 파악한다.
2. **"init 전 체크리스트"(위 step 3)를 워크트리 cwd 에서 재확인**한다 — 특히 pane 존재, 워킹트리 상태, (xreview/PR) CLI·remote·gh 인증. PHASES.md 는 이미 스테이징돼 있으니 그 완전성만 검증.
3. 그 페이즈 제목들로 phaseflow init(개인 모드 init 과 동일, `--continue-prompt "/phase-loop continue"`). 이제 cwd 가 워크트리라 상태가 올바른 네임스페이스에 안착한다.
4. **Phase 1 작업**으로 간다.

---

## CONTINUE — 다음 페이즈 이어받기

`/clear` 후 주입된 `/phase-loop continue` 로 진입하거나 사용자가 직접 호출했을 때.

```bash
bash "${SKILL_DIR}/scripts/loop.sh" pf current
```

`STATUS`/`CURSOR`/`TOTAL`/`TITLE`/`HANDOFF` 를 읽는다. `STATUS` 가 `done`/`aborted` 면 더 할 일이 없으니 보고하고 끝낸다.

`HANDOFF=` 가 가리키는 `HANDOFF.md` 와 같은 디렉토리의 `PHASES.md` 를 **반드시 읽어** 전체 계획·모드·스택 상태·이번 페이즈의 분기 base 를 파악한다. 그 다음 "페이즈 프로토콜"을 수행한다.

---

## 페이즈 프로토콜 (START Phase 1 / CONTINUE 공통)

### 1. 브랜치 확인 (팀 모드만)

이번 페이즈 브랜치는 **이미 잘려 있어야 한다** — Phase 1 은 워크트리 생성 시(`worktree-create --first-branch`), Phase 2+ 는 직전 페이즈의 완료 프로토콜(§7)에서 미리 cut 된다. 그래서 fresh 세션은 보통 **이미 올바른 브랜치 위**에 있다.

- `git branch --show-current` 가 `PHASES.md`/`HANDOFF.md` 의 이번 페이즈 브랜치와 일치하는지 **확인만** 한다.
- 어긋났거나(사용자 개입 등) 브랜치가 없으면 폴백으로 만든다: **stack** `git checkout -b <이번 브랜치> <직전 페이즈 브랜치>`, **parallel** `git checkout -b <이번 브랜치> <통합 base>`.
- 개인 모드: 브랜치 전환 없음(현재 브랜치에서 계속).

### 2. 구현

`TITLE` 페이즈의 실제 작업을 한다. 핸드오프의 `Next Action` 부터 시작.

### 3. xreview 라운드 (최대 N회, 깨끗하면 조기종료)

구현이 끝나면(미커밋 상태) 다른 에이전트로 리뷰를 돌린다.

1. **리뷰 start**: `xreview:live` 스킬을 start 로 호출한다 — `--scope working --approve auto --context "<이번 페이즈의 의도·설계결정 3~6줄>"` (reviewer 생략=반대편 도구). 의도 요약은 "왜 이렇게 짰는지" 중심, 비밀값 금지.
2. **turn 종료 후 핑 대기**(불변 원칙 4). 다른 작업을 하지 말고 끝낸다.
3. **완료 핑 수신** → `REVIEW_RESULT.md` 를 Read 해 severity 순으로 정리한다.
   - **blocking(critical/major) 이 없거나 리뷰어가 approve** → 라운드 종료, 4단계로.
   - blocking 이 있으면 → **반영(코드 수정)** 후 라운드 수를 +1.
     - 아직 최대 N 미만이면 → 1번으로 돌아가 **재리뷰**(새 xreview start).
     - 최대 N 도달이면 → 남은 미해결 항목을 `sessionflow:followup` 으로 기록하고(또는 핸드오프 Notes 에 명시) 4단계로 진행한다. (무한 루프 금지)
4. 라운드 요약(돈 횟수·반영/미해결)을 짧게 보고하고 다음 단계로.

> 리뷰 라운드는 같은 페이즈 안(=clear 전)에서 일어나므로 컨텍스트가 유지된다. 라운드 진행 상황은 in-context 로 추적한다(예: "라운드 2/2").

### 4. 커밋 (정책별)

이번 페이즈 변경분을 스테이징한다(의도치 않은 파일 제외).
- **무인(팀/`--auto`)**: 저장소 커밋 컨벤션에 맞는 메시지로 바로 커밋한다(프로젝트에 `ghflow:commit` 규약이 있으면 그 스타일로).
- **확인(개인/`--confirm`)**: 변경 요약(`git status`/`git diff --stat`)을 보여주고 **커밋해도 될지 확인**받는다. 확인 전엔 커밋하지 않고 turn 을 끝낸다. 확인되면 커밋하고 이어서 진행.

### 5. push (remote 가 있을 때만)

```bash
git push -u origin <이번 브랜치>
```
remote 가 없으면(개인 로컬) 건너뛰고 그 사실을 보고한다.

### 6. PR 생성 (팀 모드 / 명시 시)

- **stack**: `gh pr create --base <직전 페이즈 브랜치> --head <이번 브랜치> …` (Phase 1 의 base 는 통합 base).
- **parallel**: `--base <통합 base>`.
- PR 본문 상단에 **스택 표시**를 넣는다(예: `스택: #41 ← #42 ← (this)`)와 이번 페이즈 의도 요약. 프로젝트에 PR 템플릿(`ghflow:create-pr`)이 있으면 그 양식을 따른다.
- 개인 모드(또는 remote 없음)는 PR 을 건너뛴다.
- 생성된 PR 번호/URL 을 기록(핸드오프에 들어간다).

### 7. 다음 페이즈 stacked 브랜치 cut (팀 모드 / 마지막 페이즈 아닐 때)

다음 세션이 깨어날 자리를 **지금** 만든다(불변 원칙 7). 이번 페이즈를 push·PR 까지 끝낸 직후, advance 전에:

- **stack**: `git checkout -b <다음 페이즈 브랜치> <이번 브랜치>` — 다음 브랜치가 이번 브랜치 끝에 쌓인다(아직 커밋 없음 — push·PR 은 다음 페이즈가 한다).
- **parallel**: `git checkout -b <다음 페이즈 브랜치> <통합 base>`.
- 다음 브랜치명은 `PHASES.md` 의 **다음** 페이즈 항목 `브랜치:` 를 그대로 쓴다.
- 이 checkout 으로 **워킹트리가 다음 브랜치로 이동**한다 → `/clear` 후 fresh 세션이 이미 그 위에 있다(= 각 페이즈가 독립 PR 로 확정).
- **마지막 페이즈**거나 **개인 모드**면 이 단계를 건너뛴다(다음 분기 없음 / 브랜치 고정).

### 8. HANDOFF.md 작성 + 완전성 검증

`sessionflow:handoff` 규약으로 `HANDOFF.md`(= `pf current` 의 `HANDOFF` 경로)를 **다음 페이즈 기준**으로 작성한다. 표준 섹션에 더해:

```markdown
## Phase Loop Progress
- 완료: Phase {N} — {제목}  (브랜치 {branch}, PR {#NN 또는 "—"})
- 다음: Phase {N+1} — {제목}
- 모드: {team(stack)|team(parallel)|personal} / commit={auto|confirm} / xreview={돈 라운드}회
- 이어받기: `/phase-loop continue`

## Stack State   (팀 모드만)
- 워크트리: {경로}
- 완료한 페이즈 브랜치: {이번 브랜치} (PR {#NN})  ← push·PR 완료
- 현재 체크아웃: {다음 페이즈 브랜치}  ← §7 에서 미리 cut, fresh 세션이 여기서 시작
- 스택: {auth/01(#41) ← auth/02(#42) ← auth/03(여기, PR base auth/02)}
- 다음 페이즈 PR base: {이번 브랜치}
- 병합 순서: 바닥(#41)부터 bottom-up. squash 머지면 위 스택 rebase 필요(루프 밖).
```

> 이 시점엔 §7 이 이미 다음 페이즈 브랜치를 cut 하고 워킹트리를 옮겨놨다. HANDOFF 의 "현재 체크아웃"·`Current State` 는 **다음 페이즈 브랜치 기준**으로 적는다(fresh 세션이 그 위에서 깨어나므로).

**검증(불변 원칙 2):** "이 핸드오프+PHASES.md 만 보고, 대화 로그 없이, 다음 페이즈를 시작할 수 있는가?" 빠진 분기 base·PR 번호·미해결 리뷰·다음 액션이 있으면 지금 채운다. 비밀값은 적지 않는다.

### 9. advance (= 너의 마지막 행동)

```bash
bash "${SKILL_DIR}/scripts/loop.sh" pf advance --pane "$TMUX_PANE" --tool {HARNESS_NAME}
```

- 다음 페이즈가 있으면: phaseflow 가 `DELAY` 초 뒤 `/clear` → `/phase-loop continue` 를 이 pane 에 자동 주입한다.
- 마지막 페이즈였으면: `✅ 모든 페이즈 완료` 출력, 주입 없음 → 루프 종료 보고(생성된 PR 들·미해결 followup 요약).

advance 출력(자동 전진 예약됨 / 완료 / tmux 없어 수동 안내)을 **한두 줄로** 전달하고 추가 작업 없이 turn 을 끝낸다.

---

## PHASES.md 포맷

`loop.sh paths` 의 `PHASES_FILE` (= `HANDOFF.md` 와 같은 디렉토리)에 둔다. fresh 세션이 매번 읽어 계획·정책·스택을 재구성하는 단일 진실원이다.

```markdown
# Phase Loop Plan

> Created: {날짜}
> Mode: team | personal
> Commit policy: auto | confirm
> Stack: stack | parallel        (팀 모드)
> Integration base: origin/main  (팀 모드)
> Worktree: ../proj-<slug>        (팀 모드)
> Branch scheme: <slug>/NN-<short>
> xreview: reviewer={auto|claude|codex}, max-rounds=2, scope=working
> Resume: /phase-loop continue

## Phases

### Phase 1 — {제목}
- 목표: …
- 완료기준: …
- 브랜치: <slug>/01-…  (PR base: origin/main)
- 주의: …

### Phase 2 — {제목}
- 목표: …
- 완료기준: …
- 브랜치: <slug>/02-…  (PR base: <slug>/01-…)
…
```

각 페이즈의 `브랜치:` 가 그 페이즈가 올라탈 브랜치명이다. Phase N(N≥2)의 브랜치는 **Phase N-1 의 완료 프로토콜 §7 이 미리 cut** 하므로(불변 원칙 7), fresh 세션은 이 이름의 브랜치 위에서 깨어난다. 그 페이즈의 `PR base` 는 스택이면 직전 페이즈 브랜치, parallel 이면 통합 base 다.

## 디버그 / 경로

```bash
bash "${SKILL_DIR}/scripts/loop.sh" paths        # 세션/PHASES/HANDOFF/state 경로
bash "${SKILL_DIR}/scripts/loop.sh" pf paths      # phaseflow 상태/pane 도출
```

## 주의

- **상태 네임스페이스**: phase-loop 는 `…/phase-loop/` 상태를 쓰고 phase-run 의 `…/phases/` 와 분리된다. 같은 워크트리에서 둘을 동시에 돌리지 말 것(서로 다른 워크플로우).
- **pane 정확도**: advance/init 에 항상 `--pane "$TMUX_PANE"` 를 넘긴다(여러 세션 환경에서 엉뚱한 세션을 clear 하지 않도록).
- **Codex**: clear 기본 `/new` + CSI-u Enter. 다르면 `pf init … --clear-cmd '<명령>'`.
- **tmux 밖**: 자동 전진 불가 → 경계마다 사용자가 직접 `/clear` 후 `/phase-loop continue`. 팀 부트스트랩도 사용자가 워크트리에서 세션을 직접 띄운다.
- **리뷰·머지 캐스케이드는 루프 밖**: 루프는 스택을 앞으로 쌓기만 한다. 열린 PR 의 리뷰 반영과 bottom-up 머지(+필요 시 `git rebase --update-refs`)는 루프 종료 후 사람이 처리한다.
- **다음 브랜치 pre-cut**: 완료 프로토콜(§7)이 다음 페이즈 브랜치를 미리 잘라 워킹트리를 그 위로 옮긴 뒤 clear 한다 → fresh 세션은 이미 자기 PR 브랜치 위다. 첫 페이즈만 워크트리 생성 시 잘리고, 마지막 페이즈는 cut 하지 않는다. CONTINUE §1 은 "이미 올바른 브랜치인지" 확인만 하고, 어긋났을 때만 폴백으로 만든다.
- **멈춤**: `/phase-loop pause` 로 예약된 자동 전진을 취소(`resume` 재개). 개인 모드 커밋 확인 단계는 자연스러운 차단점이다.
