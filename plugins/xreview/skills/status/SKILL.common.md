---
name: status
description: "xreview:live 로 띄운 백그라운드 코드리뷰 세션들의 목록과 상태(running/done/ended/gone)를 한눈에 보여주는 스킬. 폴더·레포와 무관하게 머신 전체의 리뷰 세션을 전역 인덱스에서 조회한다. 각 항목의 slug·리뷰어·scope·레포/브랜치·시작시각·결과 경로를 출력한다. 사용자가 '리뷰 목록', '리뷰 상태', '리뷰 세션 목록', '돌고 있는 리뷰', '진행 중인 리뷰', '리뷰 현황', 'xreview status', '/xreview:status' 등을 말하면 트리거. 특정 세션만 보려면 slug 를 인자로 준다. Usage: /xreview:status [slug]"
argument-hint: "[slug]"
tools: [shell]
effort: low
model: sonnet
---

# xreview:status — 백그라운드 리뷰 세션 목록/상태

`/xreview:live` 로 띄운 리뷰 세션들의 현재 상태를 조회한다. 모든 로직은 `${PLUGIN_ROOT}/scripts/status.sh` 가 담당한다. 너(LLM)는 스크립트를 실행하고 출력을 **그대로** 사용자에게 전달한다.

## 실행

```bash
bash "${PLUGIN_ROOT}/scripts/status.sh" [slug]
```

- `$ARGUMENTS` 에 slug 가 있으면 그대로 넘겨 해당 세션만 조회한다.
- 없으면 전역 인덱스(`{HBRNESS_HOME}/xreview/live/.sessions/*.json`)의 모든 세션을 출력한다. **현재 폴더·레포와 무관하게** 머신 전체를 본다.

## 출력 항목 (스크립트가 생성)

세션마다:
- **slug** (브랜치-해시 식별자)
- **state** — `running` / `done (result ready)` / `ended (no result)` / `gone`
- **reviewer** (claude/codex), **scope** (branch/working/pr)
- **repo / branch**
- **session** (tmux 세션명), **started** (생성 시각)
- result 파일이 있으면 그 경로

## 가이드라인 (너 = LLM)

- 스크립트 출력을 재해석·축약하지 말고 그대로 보여준다. 표로 정리해 보기 좋게 만드는 것은 허용.
- 세션이 하나도 없으면 스크립트가 안내 문구를 출력한다 → 그대로 전달하고, 새 리뷰는 `/xreview:live` 로 시작하라고 덧붙인다.
- 특정 세션을 들여다보려면 `/xreview:live peek <slug>` 또는 `dock <slug>`, 종료는 `/xreview:stop <slug>` 로 안내한다.
- `done` 상태 세션의 결과를 사용자가 보고 싶어 하면 result 경로를 Read 해서 severity 순으로 요약한다. 단, **findings 에 따른 코드 자동 수정은 하지 않는다**(사용자가 명시적으로 요청할 때만).
