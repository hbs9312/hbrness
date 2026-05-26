---
name: agent-unregister
description: "agentbus 레지스트리에서 별칭을 제거한다. 인자 없이 호출하면 현재 pane 에 잡혀있는 별칭을 제거. 보통 세션을 끝내기 직전이나 다른 별칭으로 다시 등록하기 전에 호출한다. 사용자가 'agent unregister', '에이전트 해제', '등록 해제', '/agent-unregister' 등을 말하면 트리거. Usage: /agent-unregister [별칭]"
argument-hint: "[alias]"
tools: [shell]
effort: low
model: sonnet
---

# agentbus:agent-unregister — 별칭 등록 해제

## 인자

```text
agent-unregister [alias]
```

- **별칭 명시**: 해당 항목만 삭제.
- **생략**: 현재 pane 에 매핑된 모든 별칭(보통 1개)을 삭제.

## 동작

```bash
bash "${SKILL_DIR}/../agent-send/scripts/unregister.sh" "$@"
```

## 출력

```text
unregistered: frontend
```

또는 pane 기반:
```text
unregistered (pane %12): frontend
```

존재하지 않으면:
```text
no such alias: foo
no entry registered for current pane (%12)
```

## 가이드라인

- 세션을 닫기 전에 호출하지 않아도 `/agent-list` 가 stale 항목을 자동 정리하므로 필수는 아니다. 다만 의도적으로 다른 별칭으로 다시 등록할 때 깔끔하게 비우려면 유용.
- pane id 가 재활용되는 경우(거의 없지만) 에 stale 정리만 믿지 말고 명시적 unregister 권장.
