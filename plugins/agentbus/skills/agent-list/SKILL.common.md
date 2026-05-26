---
name: agent-list
description: "agentbus 레지스트리에 등록된 에이전트들의 별칭, 세션, pane, 도구 종류를 표로 출력한다. 출력 전에 죽은 pane 을 가리키는 stale 항목을 자동 정리한다. 현재 pane 의 등록은 별표(*)로 표시. 사용자가 'agent list', '에이전트 목록', '누구 등록됐어?', '/agent-list' 등을 말하면 트리거. Usage: /agent-list"
tools: [shell]
effort: low
model: sonnet
---

# agentbus:agent-list — 등록된 에이전트 표시

`registry.json` 의 모든 항목을 사람이 읽기 쉬운 표로 출력한다. 출력 직전에 `tmux list-panes -a` 와 대조해 더 이상 존재하지 않는 pane 의 항목을 자동 제거(prune)한다.

## 동작

```bash
bash "${SKILL_DIR}/../agent-send/scripts/list.sh"
```

## 출력 예

```text
pruned stale entries:
  - old-fe

ALIAS             SESSION:WINDOW          PANE      TOOL      SELF?    REGISTERED
backend           work-be:1               %18       claude    *        2026-05-25T14:32:11Z
frontend          work-fe:0               %12       claude             2026-05-25T14:30:02Z
qa                work-qa:0               %25       codex              2026-05-25T13:55:40Z
```

- `SELF?` 의 `*` 는 현재 pane 에 매핑된 별칭.
- `REGISTERED` 는 UTC 시각.

비어있으면:
```text
no agents registered. use /agent-register <alias> in each session.
```

## 가이드라인

- 사용자가 "누구 떠있어?" 같은 질문을 하면 이 스킬로 답한다.
- 등록되지 않은 pane 까지 굳이 찾아 알려줄 필요는 없다 (그건 `tmux list-panes` 의 영역).
