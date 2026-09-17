---
name: stop
description: "xreview:live 로 띄운 백그라운드 코드리뷰 세션을 종료하는 스킬. 리뷰어 세션·완료 watcher·docked pane 만 정리하고 **리뷰 내역(REVIEW_REQUEST/REVIEW_RESULT/meta)은 기본 보존**한다 — 나중에 다시 읽을 수 있다. 인자 없이 부르면 /xreview:status 목록을 먼저 보여주고 어떤 세션을 끝낼지 고르게 한다. slug 직접 지정, --all(전부), --purge(작업 디렉토리까지 삭제)도 지원. 사용자가 '리뷰 종료', '리뷰 세션 종료', '리뷰 중지', '리뷰 끝내', '리뷰 정리', '리뷰 닫아줘', 'xreview stop', '/xreview:stop' 등을 말하면 트리거. Usage: /xreview:stop [slug | --all] [--purge]"
argument-hint: "[slug | --all] [--purge]"
tools: [shell]
effort: low
model: sonnet
---

# xreview:stop — 백그라운드 리뷰 세션 종료

`/xreview:live` 로 띄운 리뷰 세션을 정리한다. 모든 로직은 `${PLUGIN_ROOT}/scripts/stop.sh` 가 담당한다. 너(LLM)는 `$ARGUMENTS` 를 보고 아래 흐름대로 디스패치한다.

## 보존 원칙 (중요)

- `stop` 은 **세션만 종료**한다: 리뷰어 세션 kill + watcher kill + docked pane 닫기 + 인덱스 항목 제거. tmux 세션이면 tmux 가, Orca 탭이면 Orca 가 닫는다.
- 다른 backend 에서 시작한 세션은 여기서 못 죽인다. 인덱스 항목은 지우되 "그쪽 환경에서 닫아야 한다"는 경고를 출력하니, 그 문구를 사용자에게 그대로 전달한다.
- **리뷰 내역은 남는다**: 작업 디렉토리(`{HBRNESS_HOME}/xreview/live/<repo>/<slug>/` 의 REVIEW_REQUEST.md / REVIEW_RESULT.md / meta.json)는 그대로 보존된다. `/xreview:status` 의 result 경로로 계속 열어볼 수 있다.
- 내역까지 지우려면 사용자가 명시적으로 `--purge` 를 줄 때만. 임의로 붙이지 말 것.

## 디스패치

`$ARGUMENTS` 를 파싱한다.

### (A) slug 또는 `--all` 이 주어진 경우 → 바로 종료

```bash
bash "${PLUGIN_ROOT}/scripts/stop.sh" <slug | --all> [--purge]
```

- 사용자가 준 인자를 그대로 넘긴다. 스크립트 출력(`stopped <slug> (kept: <path>)` 등)을 그대로 전달한다.
- `--purge` 는 사용자가 명시했을 때만 전달한다.

### (B) 인자가 비어 있는 경우 → status 먼저 보여주고 선택받기

1. 먼저 목록을 조회한다:
   ```bash
   bash "${PLUGIN_ROOT}/scripts/status.sh"
   ```
2. 출력 결과에 따라:
   - **세션이 0개**: "종료할 리뷰 세션이 없다"고 알리고 끝낸다. (새 리뷰는 `/xreview:live`)
   - **세션이 1개**: 그 세션을 보여주고 "이 세션을 종료할까요?" 확인을 받는다. 확인되면 `stop.sh <slug>` 실행.
   - **세션이 여러 개**: 목록을 보여주고 어떤 slug 를 종료할지(또는 `--all`) 사용자에게 물어본다. 답을 받으면 해당 인자로 `stop.sh` 실행.
3. 임의로 `--all` 을 자동 선택하지 말 것. 다건일 때는 반드시 사용자 선택을 받는다.

## 가이드라인 (너 = LLM)

- 종료 후 스크립트 출력에 보존 경로(`kept: ...`)가 있으면 사용자에게 그대로 보여줘, 내역이 남아있음을 알린다.
- `--purge` 로 내역까지 지우는 것은 되돌릴 수 없으니, 사용자가 직접 요청하지 않는 한 절대 붙이지 않는다.
- 종료 대상이 `done` 상태(결과 준비됨)인데 사용자가 결과를 아직 안 봤다면, 종료 전에 result 를 읽어줄지 가볍게 제안할 수 있다(강요하지 않음).
- 세션 상태를 보고 싶을 뿐이면 `/xreview:status`, 진행 상황을 들여다보려면 `/xreview:live peek|dock` 로 안내한다.
