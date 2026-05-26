---
name: agent-inbox
description: "현재 별칭의 mailbox(다른 에이전트들이 mailbox 경로로 보낸 메시지) 를 조회·열람·읽음 처리한다. direct 경로로 들어온 짧은 메시지는 휘발성이라 inbox 에 남지 않으므로 여기서 보이지 않는다. 사용자가 'agent inbox', '받은 메시지', '메일박스 봐줘', '/agent-inbox' 등을 말하면 트리거. Usage: /agent-inbox [--alias <name>] [list | show <id> | mark <id> | clear]"
argument-hint: "[list|show <id>|mark <id>|clear]"
tools: [shell, file:read]
effort: low
model: sonnet
---

# agentbus:agent-inbox — mailbox 조회/관리

`/agent-send --json` 또는 `/agent-send --file` 또는 길이 임계치를 넘은 메시지가 `~/.hbrness/agentbus/inbox/<alias>/` 에 파일로 쌓인다. 이 스킬로 목록을 보고 열고 읽음 처리한다.

## 인자

```text
agent-inbox [--alias <name>] [list | show <id> | mark <id> | clear]
```

- **`--alias <name>`**: 어느 inbox 를 볼지. 생략 시 현재 pane 에 매핑된 별칭을 자동 사용.
- **`list`** (기본): 메시지 목록을 표로 출력. 읽음 마커(`.read` 파일) 가 있으면 `[x]`, 없으면 `[ ]`.
- **`show <id>`**: 메시지 JSON 전체 출력. id 는 short hex (예: `a3f9`).
- **`mark <id>`**: 읽음 마커 생성 (`<파일>.read` touch).
- **`clear`**: 해당 inbox 의 모든 메시지 삭제. tty 에서 호출되면 확인 프롬프트.

## 동작

```bash
bash "${SKILL_DIR}/../agent-send/scripts/inbox.sh" "$@"
```

## 출력 예

```text
inbox: backend  (/Users/.../.hbrness/agentbus/inbox/backend)
  [ ] a3f9  2026-05-25T14:40:12Z  from=frontend  kind=json      {"context":"race condition 우려"...
  [x] b1c2  2026-05-25T14:35:00Z  from=frontend  kind=text      로그인 API 응답 스키마 확정됐어?

show:  agent-inbox show <id>
mark:  agent-inbox mark <id>
```

## 가이드라인

- 사용자가 "받은 메시지" 라고 말하면 list 부터 보여주고, 사용자가 골라달라거나 처리해달라고 하면 show + mark 흐름으로 안내.
- show 결과는 JSON 그대로다. 본문(`body`) 만 보고 싶다고 하면 `jq -r '.body'` 로 추출해서 보여줘도 좋다 — 단, 그건 사용자 요청이 있을 때만.
- `clear` 는 비가역이므로, 사용자가 명시적으로 요청하지 않는 한 자동 실행하지 말 것.
- direct 경로 메시지는 휘발성이라 여기 안 나타난다. "보냈는데 안 보인다" 면 발신 쪽이 < 500자라 direct 로 갔거나 (이 경우 수신 pane 의 대화 로그에 이미 user input 으로 들어가 있음), 발신 자체가 실패한 경우.
