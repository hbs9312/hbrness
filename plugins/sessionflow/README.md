# sessionflow

세션 간 컨텍스트를 보존·재개하기 위한 스킬 모음. Claude Code 와 Codex CLI 가 **동일한 저장소(`HANDOFF.md` / `followups/`)를 공유**하므로, 한 도구에서 작성한 내용을 다른 도구에서 그대로 이어 작업할 수 있습니다. `phase-run` 은 여기서 한 발 더 나아가, 페이즈 경계마다 컨텍스트를 비우고 새 세션이 핸드오프를 읽어 자동으로 이어받게 합니다.

## 스킬

| 스킬 | 트리거 | 역할 | 범위 |
|---|---|---|---|
| `followup` | `/followup [-m\|-o] [메시지]` | 현재 세션에서 발견한 **후속 조치** 항목을 `followups/` 디렉토리(`INDEX.md` + 항목별 상세 파일)에 누적 기록. TODO·결정 보류·아이디어·발견된 이슈. 기본 동작은 merge. | 프로젝트 단위 (워크트리·세션 무관) |
| `followup-clear` | `/followup-clear [-y]` | 누적된 followup 을 한 번에 비움. `followups/` 디렉토리 삭제 + 양쪽 `MEMORY.md` 의 `## Followups` 섹션 제거. | 프로젝트 단위 |
| `handoff` | `/handoff [-m\|-o] [메시지]` | 현재 워크트리/세션의 **in-flight 컨텍스트** (편집중 파일·마지막 명령·실패한 에러·다음 한 줄) 를 `HANDOFF.md` 로 직렬화. 다음 세션이 즉시 이어받을 수 있게. | 워크트리 단위 (메인 = 워크트리의 베이스) |
| `handoff-clear` | `/handoff-clear [-y] [--all]` | 현재 위치(워크트리/메인)의 `HANDOFF.md` 삭제 + `MEMORY.md` 의 해당 라인 정리. `--all` 로 프로젝트 전체 핸드오프 일괄 정리. | 워크트리 단위 (또는 `--all` 시 프로젝트 전체) |
| `phase-run` | `/phase-run [continue\|pause\|resume\|stop\|status\|reset] \| <계획>` | 작업을 페이즈로 분해해, 각 페이즈가 끝나면 자기 pane 에 `/clear` + `/phase-run continue` 를 자동 주입 → 새 세션이 `HANDOFF.md` 를 읽고 다음 페이즈를 이어받게 한다. 컨텍스트 누적을 경계마다 리셋. 자동 커밋은 하지 않음. | 워크트리 단위 (handoff 와 동일 경로 공유) |
| `phase-loop` | `/phase-loop [continue\|pause\|resume\|stop\|status\|reset] \| <구현 계획>` | `phase-run` 엔진 위에 각 페이즈 경계마다 **구현 → xreview 리뷰 N라운드 → 커밋 → push → PR → 핸드오프** 를 끼워 넣어, 모든 페이즈(=PR 단위)가 끝날 때까지 자동 반복하는 루프. 개인=브랜치 직접, 팀=워크트리+스택 PR. 커밋은 모드별(팀=무인 / 개인=확인). | 워크트리 단위 (phase-run 과 분리된 `phase-loop` 상태 네임스페이스, HANDOFF 는 공유) |

### phase-run 동작 개요

```
/phase-run <계획>
  └ 페이즈 분해 → 1회 확인 → init → Phase 1 작업
  └ 완료: HANDOFF.md 작성·검증 → advance → (DELAY초 후) detached injector 가 자기 pane 에
           /clear + /phase-run continue 주입
[새(비워진) 세션] /phase-run continue → HANDOFF.md 읽고 Phase 2 … cursor>total 이면 종료
```

- **자기 pane 주입**: `$TMUX_PANE`(이 프로세스가 사는 pane)을 1순위로 사용 — `tmux display-message`(사용자가 보는 pane)는 여러 세션 환경에서 엉뚱한 세션을 clear 할 수 있어 쓰지 않음.
- **무인이되 멈출 수 있음**: 경계마다 차단형 확인은 없지만, `/phase-run pause` 한 줄로 예약된 자동 전진을 취소할 수 있음(`resume` 으로 재개).
- **상태**: `~/.hbrness/sessionflow/<project-key>/[worktrees/<wt>/]phases/` (`state.env` + `phases.tsv`), 로직은 전부 `scripts/phaseflow.sh`.
- **Codex**: clear 기본 `/new` + CSI-u Enter 제출. 버전이 다르면 `init --clear-cmd` 로 override.

### phase-loop 동작 개요

```
/phase-loop <구현 계획>
  └ 모드 추정→확인 → 페이즈(=PR 단위) 분해→1회 확인
  └ 개인: 그 자리에서 init → Phase 1
  └ 팀:   워크트리+첫 브랜치 생성 → PHASES.md 스테이징 → "cd 후 /phase-loop start" 안내 후 멈춤(수동 부트스트랩)
[각 페이즈] 구현 → xreview N라운드(깨끗하면 조기종료) → 커밋(팀=무인/개인=확인) → push → PR(stack base) → HANDOFF 작성 → advance
  └ advance → (DELAY초 후) /clear + /phase-loop continue 자동 주입 → 새 세션이 다음 페이즈
[모든 페이즈 완료] 종료 보고(생성된 PR·미해결 followup)
```

- **엔진 재사용**: 상태머신·tmux 주입은 `phase-run` 의 `scripts/phaseflow.sh` 를 그대로 쓰되, `PHASEFLOW_STATE_DIR_NAME=phase-loop` 로 상태를 분리한다(HANDOFF.md 경로는 워크트리 단위라 공유). 보조 로직(모드 감지·워크트리 생성·경로·forward)은 `skills/phase-loop/scripts/loop.sh`.
- **모드별 자동화**: 팀(워크트리+PR)은 PR 이 리뷰 게이트라 무인, 개인(브랜치 직접)은 커밋 전 확인. `--auto`/`--confirm` 로 override.
- **스택 PR**: 같은 워크트리에서 브랜치만 페이즈마다 직전 브랜치 HEAD 에서 분기 → PR base 를 직전 브랜치로. 리뷰 반영·bottom-up 머지·rebase 캐스케이드는 **루프 밖**(사람/도구) 책임.
- **상태**: `~/.hbrness/sessionflow/<project-key>/[worktrees/<wt>/]phase-loop/` + 계획은 같은 디렉토리의 `PHASES.md`.

## followup vs handoff — 언제 무엇을 쓰는가

| | `followup` | `handoff` |
|---|---|---|
| 시나리오 | "이 버그 발견했는데 이번엔 못 고치겠다 — 나중에 처리해야 됨" | "지금 빌드 에러 잡는 중인데 컨텍스트 길어져서 끊김 — 새 세션에서 그대로 이어가야 함" |
| 누가 읽나 | 다음 세션 시작 시점, 또는 백로그 정리 시점 | 바로 다음 세션 — 그 자리에서 작업 재개 |
| 수명 | 항목별로 Resolved 처리하며 영속 누적 | 작업 재개 후 보통 삭제 |
| 저장 | `followups/` 디렉토리 (1 per project) | `HANDOFF.md` (1 per worktree) |

## 저장 경로 (Tier 1 — 도구 무관 공유)

```
~/.hbrness/sessionflow/<project-key>/
├── followups/                            # 프로젝트 단위 후속 조치
│   ├── INDEX.md                          # 항목 목록 + 한 줄 설명 + 상세 링크 (진입점)
│   └── <slug>.md                         # 항목별 상세 파일
├── HANDOFF.md                            # 메인 레포에서 호출한 핸드오프
├── PHASES.md                             # phase-run/phase-loop 계획 (있을 때)
├── phases/                               # phase-run 상태 (state.env + phases.tsv)
├── phase-loop/                           # phase-loop 상태 (phase-run 과 분리된 네임스페이스)
└── worktrees/
    └── <wt-name>/                        # 각 워크트리별 (HANDOFF.md, PHASES.md, phases/, phase-loop/)
```

> 이전 버전(≤0.2.x)은 프로젝트당 단일 `FOLLOWUPS.md` 를 썼습니다. 그 파일이 남아 있으면 `followup` 스킬이 다음 실행 때 위 `followups/` 구조로 자동 마이그레이션하고 레거시 파일을 제거합니다.

- `<project-key>` = 프로젝트 절대경로의 `/` 를 `-` 로 치환 (leading dash 유지).
  예: `/Users/seok/development/my-app` → `-Users-seok-development-my-app`
- `<wt-name>` = `basename "$(git rev-parse --git-dir)"` — git 워크트리 디렉토리명
- 양쪽 하네스(Claude / Codex)에서 동일 파일을 읽고 씀.

## MEMORY.md 갱신 (Tier 2 — 하네스별 자동로드 위치)

스킬은 동시에 양쪽 하네스의 MEMORY.md 의 `## Followups` 또는 `## Handoff` 섹션을 갱신해 위 공유 경로를 가리키게 합니다.

| 하네스 | MEMORY.md 위치 |
|---|---|
| Claude | `~/.claude/projects/<project-key>/memory/MEMORY.md` |
| Codex | `~/.codex/memories/<project-key>/MEMORY.md` |

스킬 본문은 `{CLAUDE_MEMORY_PREFIX}` / `{CLAUDE_MEMORY_SUFFIX}` 와 `{CODEX_MEMORY_PREFIX}` / `{CODEX_MEMORY_SUFFIX}` placeholder 로 양쪽 경로를 표현합니다.

## 동작 보장

- **install** 은 SKILL.md 만 배치합니다. MEMORY.md 는 스킬이 실제로 실행될 때만 갱신됩니다.
- `followup` 과 `handoff` 는 서로의 파일을 절대 건드리지 않습니다. clear 스킬도 마찬가지입니다.
- `handoff` 는 워크트리 격리 — 같은 프로젝트의 메인/워크트리A/워크트리B 가 서로 덮어쓰지 않습니다.
- `followup` 은 프로젝트 단위 — 어느 워크트리에서 호출해도 동일한 `followups/` 디렉토리에 누적됩니다.
