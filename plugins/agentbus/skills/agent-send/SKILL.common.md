---
name: agent-send
description: "다른 tmux 세션에 등록된 에이전트(예: frontend, backend)에게 메시지를 보낸다. 짧은 메시지는 tmux send-keys 로 상대 프롬프트에 직접 주입되고, 긴 메시지나 --json/--file 은 ~/.hbrness/agentbus/inbox/<수신자>/ 에 파일로 저장된 뒤 알림만 주입된다. 도구 무관(claude/codex 어느 쪽에서도 동일 동작). 사용자가 'agent send', '에이전트한테 메시지', 'frontend 한테 보내줘', '/agent-send', 'tmux 에이전트 통신' 등을 말하면 트리거. Usage: /agent-send <별칭|raw-target> [--from <alias>] [--json | --file <path>] [--strict] [--kind <k>] <message>"
argument-hint: <to> [--json|--file <path>] [--strict] <message>
tools: [shell]
effort: low
model: sonnet
---

# agentbus:agent-send — 다른 세션의 에이전트에게 메시지 보내기

서로 다른 tmux 세션·window·pane 에 떠있는 코딩 에이전트(Claude / Codex / 일반 셸) 들끼리 1:1 로 메시지를 주고받는 명령. 사용자가 명시적으로 `/agent-send <누구> "<무엇>"` 을 호출하면 그대로 전송한다.

이 스킬은 다음 자매 스킬들과 같은 `scripts/` 디렉토리를 공유한다:
- `/agent-register` — 자기 자신을 별칭으로 등록
- `/agent-unregister` — 별칭 해제
- `/agent-list` — 등록 목록 + stale 정리
- `/agent-inbox` — mailbox 메시지 조회

## 인자

`$ARGUMENTS` 에서 파싱한다. `send.sh` 가 모든 파싱을 책임지므로, 사용자 입력을 그대로 전달하면 된다.

```text
agent-send <to> [--from <alias>] [--kind <k>] [--json | --file <path>] [--strict] <message>
```

- **`<to>`**: 수신자 별칭 (예: `backend`) 또는 raw tmux target (`%paneId`, `session:window`, `session:window.pane`).
- **`--from <alias>`**: 발신자 별칭. 생략 시 현재 pane 으로 등록된 alias 를 자동 탐지, 그것도 없으면 `unknown`.
- **`--kind <k>`**: mailbox 파일에 기록되는 자유 태그. 기본 `text`, `--json` 이면 `json`, `--file` 이면 `file`.
- **`--json`**: 본문을 JSON 으로 간주, **강제 mailbox 경로**.
- **`--file <path>`**: 파일 내용을 본문으로, **강제 mailbox 경로**. 선행 인자가 있으면 라벨로 첨부.
- **`--strict`**: 수신 pane 의 `current_command` 가 `claude|codex|node|python|bash|...` 가 아니면 거절.
- **`<message>`**: 본문. stdin 으로도 받음.

길이 기반 자동 분기 (mailbox 강제 플래그가 없을 때):
- 본문이 `$AGENTBUS_DIRECT_THRESHOLD` (기본 500자) 미만 → **direct**: 상대 pane stdin 에 `[from <발신자> @ HH:MM] <body>` 한 줄 주입.
- 그 이상 → **mailbox**: `~/.hbrness/agentbus/inbox/<수신자>/<TS>_<발신자>_<id>.json` 작성, 상대에는 짧은 알림만 주입.

## 실행

```bash
bash "${SKILL_DIR}/scripts/send.sh" "$@"
```

표준 출력은 한 줄짜리 JSON 으로 결과를 알린다:
- direct: `{"route":"direct","id":"...","bytes":N,"recipient":"%paneId","display":"alias:..."}`
- mailbox: `{"route":"mailbox","id":"...","path":"...","recipient":"%paneId","display":"..."}`

## 사용자 시나리오

### 1. 짧은 질문 (direct 경로)

```
> /agent-send backend "로그인 API 응답 스키마 확정됐어? 프론트에서 타입 짜야 해서"
```

내부적으로:
1. `registry.json` 에서 `backend` 의 pane 조회.
2. 본문 < 500자 → direct.
3. `tmux send-keys -t %18 -l '[from frontend @ 14:35] 로그인 API 응답 스키마...'` + Enter.
4. backend 세션의 Claude 가 user input 으로 그 문장을 받음.

backend 가 회신하려면 같은 명령:
```
> /agent-send frontend "응답 스키마 확정. types/auth.ts 에 LoginResponse 정의해뒀어"
```

### 2. 구조화된 데이터 (mailbox 경로)

```
> /agent-send backend --json '{"kind":"code-review-request","files":["src/api/login.ts"],"context":"race condition 우려"}'
```

→ `~/.hbrness/agentbus/inbox/backend/2026-05-25T14-40-12_frontend_a3f9.json` 작성, backend 세션에는 `[agentbus] new message from frontend (kind=json, id=a3f9): <경로> — Read 로 열어서 확인해줘.` 만 주입됨.

### 3. 파일 통째로 전달

```
> /agent-send backend --file ./draft-spec.md "이 명세서 백엔드 관점에서 검토 부탁"
```

본문에는 라벨 + 파일 내용이 합쳐져 mailbox 에 저장됨.

### 4. 안전 모드

```
> /agent-send backend --strict "긴급 회의 한 시간 뒤"
```

수신 pane 이 빈 셸이거나 vim 같은 비-에이전트 프로세스면 거절. 의도하지 않은 곳에 텍스트가 들어가는 사고 방지.

## 가이드라인 (당신 = LLM)

- 사용자가 `/agent-send` 를 호출했을 때만 동작한다. **다른 에이전트의 메시지를 받았다고 해서 자동으로 회신하지 말 것** — 사용자에게 보여주고, 사용자가 원하면 그때 다시 `/agent-send` 를 호출하게 안내한다.
- 본문에 따옴표·줄바꿈·특수문자가 섞여 있으면 그대로 `send.sh` 에 args 로 전달한다 (shell 의 인자 escaping 은 사용자가 입력한 따옴표가 책임진다). 본문이 정말 복잡하면 `--file` 사용을 권장.
- 수신자가 존재하지 않으면 `send.sh` 가 죽고 stderr 로 이유를 출력한다. `/agent-list` 로 확인하라고 안내한다.
- **자기 자신에게 보내기**는 lib 단에서 차단된다 (loop 방지).

## 환경 변수

- `AGENTBUS_HOME` — 기본 `~/.hbrness/agentbus`. 테스트 격리용.
- `AGENTBUS_DIRECT_THRESHOLD` — direct/mailbox 분기 바이트 수. 기본 500.
- `AGENTBUS_TMUX_SUBMIT_MODE` — `Enter` 또는 `codex-enhanced-enter`. 기본은 codex 환경변수 감지해서 자동 선택.
