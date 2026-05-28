---
name: agent-register
description: "현재 tmux 세션·pane 을 별칭(예: frontend, backend)으로 agentbus 레지스트리에 등록한다. 등록되면 다른 세션에서 /agent-send <별칭> 으로 이 세션에 메시지를 보낼 수 있다. 보통 새 세션을 띄운 직후 한 번 호출한다. 사용자가 'agent register', '에이전트 등록', '나를 frontend 로 등록해줘', '/agent-register' 등을 말하면 트리거. Usage: /agent-register <별칭> [--tool claude|codex|shell] [--pane <%paneId>]"
argument-hint: <alias> [--tool claude|codex|shell]
tools: [shell]
effort: low
model: sonnet
---

# agentbus:agent-register — 현재 세션을 별칭으로 등록

`/agent-send <별칭>` 의 수신처가 될 수 있도록, 현재 tmux pane 을 사람이 읽기 좋은 별칭으로 레지스트리에 등록한다.

## 인자

```text
agent-register <alias> [--tool claude|codex|shell] [--pane <%paneId>]
```

- **`<alias>`**: `[A-Za-z0-9_-]+`. 예: `frontend`, `backend`, `fe-v2`, `qa_bot`.
- **`--tool`**: 메타 태그. 생략 시 자동 감지 (CODEX_THREAD_ID 등 환경변수 → `codex`, 그 외 `claude` 등).
- **`--pane <%paneId>`**: 보통 생략. 현재 pane 이 아닌 다른 pane 을 등록할 때만 (드뭄).

## 동작

```bash
bash "${SKILL_DIR}/../agent-send/scripts/register.sh" "$@"
```

내부 절차:
1. `TMUX_PANE` 또는 `tmux display-message -p '#{pane_id}'` 로 현재 pane id 획득.
2. `tmux display-message -p` 로 session/window/cmd/pid 조회.
3. 동일 별칭이 이미 **다른 살아있는 pane** 에 잡혀있으면 거절 (덮어쓰기 금지).
4. 같은 pane 에 잡혀있던 다른 별칭은 자동 제거 (한 pane = 한 별칭 원칙).
5. `~/.hbrness/agentbus/registry.json` 에 atomic 머지 (flock 또는 mkdir 락).

## 출력

```text
registered: frontend
  session:  work-fe
  window:   0
  pane:     %12
  tool:     claude
  pid:      4521
registry: /Users/.../.hbrness/agentbus/registry.json
```

## 사용 시점

- 새 tmux 세션에서 Claude/Codex 를 띄운 직후 한 번.
- 세션이 재시작되면 pane id 가 바뀌므로 다시 등록.
- 이미 등록된 상태로 다시 호출해도 멱등 (같은 pane → 같은 별칭이면 그대로 갱신).

## 가이드라인

- 별칭 작명은 **역할 기반** (`frontend`, `backend`, `qa`, `infra`) 이 좋다. 도구 이름(`claude1`, `claude2`) 은 추후 도구를 바꿨을 때 혼란을 준다.
- 자동 자기 등록 욕심을 내지 말 것 — 사용자가 명시적으로 호출했을 때만 등록한다. 다른 스킬 안에서 묵시적으로 호출하지 말 것.

## Troubleshooting

### `cannot query tmux panes: ... (Operation not permitted)` (Codex 샌드박스)

증상:
```text
agentbus: cannot query tmux panes: error connecting to /private/tmp/tmux-501/default (Operation not permitted). Re-run with tmux access (escalated permission, or outside the Codex sandbox).
```

원인: Codex 등 샌드박스 안에서는 호스트의 tmux 소켓(`/private/tmp/tmux-501/default` 등)에 접근할 수 없어 `tmux display-message` / `list-panes` 가 `EPERM` 으로 실패한다. pane 이 실제로 없는 것이 아니라, 권한 때문에 *확인 자체가 안 되는* 상황이다.

대응:
1. Codex 에서 register/list/send 명령을 escalated 권한으로 재실행. (예: `with_escalated_permissions` 옵션, 또는 샌드박스 밖 셸에서 실행.)
2. 그래도 등록을 못 하면 호스트 tmux 세션 안의 다른 도구(예: Claude Code) 에서 같은 명령을 실행해 레지스트리에 채워 넣는다. 일단 들어가면 다른 에이전트들은 `~/.hbrness/agentbus/registry.json` 만 읽으면 되기 때문에 송수신은 계속 가능하다.

진짜로 pane 이 없는 경우와 권한 문제는 메시지로 구분된다:

| 메시지 | 의미 |
|---|---|
| `agentbus: pane %NN does not exist` | tmux 서버는 정상이고 해당 pane 만 실제로 없음 |
| `cannot query tmux panes: ... Operation not permitted ...` | 샌드박스/권한으로 tmux 자체 접근 불가 |
| `cannot query tmux: tmux server not reachable (...)` | tmux 서버 자체가 안 떠 있음 |
| `not inside tmux — set TMUX or pass --pane` | tmux 세션 밖에서 실행 (`TMUX` 미설정) |

### `lock timeout on ...`

`~/.hbrness/agentbus/.lock` 관련 메시지가 다음 중 어떤 형태인지 본다:

- `lock file disappeared mid-wait — retry`: 다른 agentbus 호출이 정상 종료한 직후 일시적 경합. 그대로 재시도하면 보통 풀린다.
- `lock dir exists — likely stale from a prior crash. ... rmdir ...`: 이전 호출이 비정상 종료. 실행 중인 agentbus 가 없다면 안내된 `rmdir` 후 재시도.
- `is not writable`: `$AGENTBUS_HOME` 의 소유권/권한 문제. `ls -ld ~/.hbrness/agentbus` 로 확인.
