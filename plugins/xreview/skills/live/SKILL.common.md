---
name: live
description: "현재 코딩 에이전트와 다른 에이전트(claude↔codex)를 tmux 백그라운드 세션으로 열어, 현재 브랜치의 diff 를 읽기 전용으로 코드리뷰시키는 스킬. 리뷰어는 detached tmux 세션에서 돌고, 이 세션은 평소엔 실행 여부만 보이다가 완료되면 핑을 받는다. 원할 때 popup(peek) 또는 split pane(dock) 으로 진행 상황을 들여다보고 서로 전환할 수 있다. 무료 PR 봇 대신 로컬에서 다른 모델로 리뷰받고 싶을 때 사용. 사용자가 '백그라운드 리뷰', '다른 에이전트로 리뷰', '라이브 리뷰', 'codex 한테 리뷰 시켜줘', 'claude 로 리뷰', '리뷰 팝업', '/xreview:live' 등을 말하면 트리거. Usage: /xreview:live [start] [--reviewer claude|codex] [--scope branch|working|pr] [--base <ref>] [--approve auto|manual] [--context <text>] | peek|dock|undock|status|stop [slug]"
argument-hint: "[start|peek|dock|undock|status|stop] [--reviewer ..] [--scope ..] [slug]"
tools: [shell]
effort: low
model: sonnet
---

# xreview:live — 다른 에이전트로 백그라운드 코드리뷰

지금 돌고 있는 코딩 에이전트가 **반대편 에이전트**(claude면 codex, codex면 claude)를 별도 tmux 세션으로 띄워, 현재 브랜치의 변경분을 읽기 전용으로 리뷰하게 한다. 리뷰어는 백그라운드 detached 세션에서 독립 실행되고, 이 세션(launcher)은 완료 시 한 줄 핑만 받는다. 진행 상황은 **popup(peek)** 또는 **split pane(dock)** 으로 언제든 들여다볼 수 있고 서로 전환된다.

이 스킬은 `${SKILL_DIR}/scripts/` 의 스크립트들이 모든 로직을 담당한다. 너(LLM)는 `$ARGUMENTS` 의 첫 토큰으로 **액션**을 정하고 해당 스크립트를 실행한 뒤, 출력을 사용자에게 그대로 전달한다.

## 액션 디스패치

`$ARGUMENTS` 의 첫 단어가 액션이다. 없거나 플래그로 시작하면 **start** 로 간주한다.

| 액션 | 실행 |
|------|------|
| `start`(기본) | `bash "${SKILL_DIR}/scripts/start.sh" --current-tool {HARNESS_NAME} <나머지 인자>` |
| `peek` | `bash "${SKILL_DIR}/scripts/view.sh" peek [slug]` |
| `dock` | `bash "${SKILL_DIR}/scripts/view.sh" dock [slug]` |
| `undock` | `bash "${SKILL_DIR}/scripts/view.sh" undock [slug]` |
| `status` | `bash "${SKILL_DIR}/scripts/status.sh" [slug]` |
| `stop` | `bash "${SKILL_DIR}/scripts/stop.sh" [slug] [--purge] / --all` |

> **중요**: `start` 호출 시 반드시 `--current-tool {HARNESS_NAME}` 를 넘긴다. 이 값으로 리뷰어(반대편 도구)와 완료 핑의 submit 방식이 결정된다. 사용자가 `--reviewer` 로 명시하면 그게 우선한다.

### start 플래그 (start.sh 로 그대로 전달)

- `--reviewer claude|codex` — 리뷰어 지정. 생략 시 현재 도구의 반대편.
- `--scope branch|working|pr` — 리뷰 대상. 기본 `branch`(현재 브랜치 vs 자동 감지 base). `working`=미커밋 변경, `pr`=`gh pr diff`.
- `--base <ref>` — branch 스코프의 base 를 수동 지정.
- `--approve auto|manual` — 기본 `auto`(hands-off, 리뷰어가 승인 없이 진행). `manual`이면 리뷰어가 승인을 물어봄(peek 으로 직접 승인).
- `--context <text>` — 리뷰어에게 전달할 추가 상황 설명.
- `--title <text>` — 리뷰 제목.
- `--launch-cmd '<cmd>'` — (고급) claude/codex 대신 임의의 에이전트 명령으로 실행. seed 프롬프트가 뒤에 붙는다. 다른 CLI(예: 래퍼·사내 도구)로 확장할 때.

## 실행 흐름

### start (리뷰 시작)
1. 위 표대로 `start.sh` 를 실행한다. 스크립트가 base 감지 → diff 수집 → `code` 프리셋 주입 → `REVIEW_REQUEST.md` 작성 → detached 세션 `xrev-<slug>` 로 리뷰어 실행 → 완료 watcher 기동까지 전부 처리한다.
2. 스크립트 출력(세션명/slug/요청·결과 경로/peek·dock·status·stop 안내)을 사용자에게 그대로 보여준다.
3. **리뷰가 끝나면** launcher 세션(=지금 너)에 `[xreview:live] 리뷰 완료 (<slug>) — Read <경로> 로 ...` 핑이 user input 으로 들어온다. 그때 `REVIEW_RESULT.md` 를 Read 해서 severity 순으로 요약해 보여준다.

### peek / dock / undock (들여다보기)
- `peek` → 팝업으로 리뷰어 세션을 본다(닫아도 백그라운드 유지).
- `dock` → 현재 창에 split pane 으로 붙인다.
- `undock` → 붙인 pane 을 닫는다(리뷰어는 계속 백그라운드).
- slug 를 생략하면 활성 세션이 1개일 때 자동 선택, 여러 개면 목록을 보여주고 slug 를 요청한다.

### status / stop
- `status` → 모든 리뷰 세션과 상태(running/done/ended/gone)를 출력.
- `stop` → 세션·watcher·docked pane 정리. 기본은 결과 파일 보존, `--purge` 면 작업 디렉토리까지 삭제. `--all` 로 전부 정리.

## 가이드라인 (너 = LLM)

- 완료 핑을 받으면 **결과를 읽어 요약**까지 한다. 단, **리뷰 findings 에 따른 코드 자동 수정은 하지 않는다** — 사용자가 명시적으로 "고쳐줘" 라고 할 때만. (xreview 플러그인 공통 규칙)
- 리뷰어 출력을 재해석·왜곡하지 말고, severity(critical/warning/info)와 file:line, VERDICT 를 보존해 정리한다.
- tmux 밖에서 호출되면 `start.sh` 가 죽고 안내를 출력한다 → 사용자에게 tmux 세션에서 실행하라고 알린다.
- 리뷰어 CLI(claude/codex)가 PATH 에 없으면 스크립트가 거절한다 → 설치/PATH 안내.
- 사용자가 그냥 "리뷰해줘" 라고만 하고 **블로킹 동기 리뷰**(결과를 바로 받는)를 원하면 이 스킬이 아니라 `xreview:review` 가 맞다. 이 스킬은 "백그라운드로 띄워 지켜보는" 인터랙티브 흐름 전용이다.

## 동작 방식 메모

- 리뷰어는 `xrev-<slug>` detached 세션에 산다. peek(팝업)·dock(split)은 `env -u TMUX tmux attach` 로 그 세션을 보는 **비파괴적 viewport** 일 뿐이라, 닫아도 리뷰어 프로세스는 죽지 않는다.
- 읽기 전용 보장: codex 리뷰어는 `-s workspace-write` + cwd=작업디렉토리라 레포 쓰기를 샌드박스가 차단한다. claude 리뷰어는 레포를 `--add-dir` 로 읽기만 추가하고 결과는 작업디렉토리에 쓴다(읽기 전용은 프롬프트로 강제).
- 저장 위치(Tier 1): `~/.hbrness/xreview/live/<repo>/<slug>/` (REVIEW_REQUEST.md, REVIEW_RESULT.md, meta.json), 인덱스 `~/.hbrness/xreview/live/.sessions/<slug>.json`.

## 환경 변수

- `XRLIVE_HOME` — 기본 `~/.hbrness/xreview/live`. 테스트 격리용.
- `XRLIVE_WATCH_TIMEOUT` — watcher 최대 대기 초. 기본 7200(2h).
- `XRLIVE_WATCH_INTERVAL` — 폴링 간격 초. 기본 3.
- `XRLIVE_LAUNCH_OVERRIDE` — `--launch-cmd` 의 환경변수 버전(임의 리뷰어 명령).
