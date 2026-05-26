# agentbus

서로 다른 tmux 세션·window·pane 에서 돌고 있는 AI 코딩 에이전트들끼리 1:1 로 메시지를 주고받는 플러그인.

## 왜 필요한가

- 프론트엔드 작업하는 Claude 세션과 백엔드 작업하는 Claude 세션을 동시에 띄워놓고 있을 때, "로그인 API 응답 스키마 확정됐어?" 같은 질문을 한 쪽에서 다른 쪽으로 넘기고 싶다.
- 도구가 달라도 (한 쪽은 Claude, 다른 쪽은 Codex) 동일한 메커니즘이어야 한다.
- 사용자가 양쪽 세션을 번갈아 보면서 직접 복사·붙여넣기 하지 않아도 되어야 한다.

## 메커니즘

1. **별칭 레지스트리**: 각 에이전트가 시작 시 `frontend`, `backend` 같은 별칭으로 자기 자신을 등록 (`~/.hbrness/agentbus/registry.json`). 별칭 → tmux pane id 매핑.
2. **메시지 전송**: `/agent-send <별칭> "<메시지>"` 로 보낸다.
   - **짧은 메시지 (< 500자)**: `tmux send-keys -l "<msg>"` + Enter 로 상대 세션 stdin 슬롯에 직접 주입. 받는 에이전트는 그냥 user input 으로 인식.
   - **긴 메시지 / `--json` / `--file`**: `~/.hbrness/agentbus/inbox/<수신자>/<TS>_<발신자>_<id>.json` 으로 작성하고, tmux 로는 "새 메시지 도착: <경로>" 알림만 주입. 받는 에이전트가 Read 로 직접 열어 처리.
3. **회신**: 양방향 RPC 가 아니라 받은 쪽이 다시 `/agent-send <발신자> "<응답>"` 하면 된다.

## 스킬

- `/agent-register <별칭> [--tool claude|codex|shell]` — 현재 세션을 별칭으로 등록.
- `/agent-unregister [별칭]` — 등록 해제. 별칭 생략 시 현재 pane 의 등록을 제거.
- `/agent-list` — 등록된 에이전트와 stale 정리 결과 출력.
- `/agent-send <별칭|raw-target> [--json | --file <경로>] [--strict] <메시지>` — 메시지 전송.
- `/agent-inbox [mark <id>] [show <id>]` — 받은 mailbox 메시지 조회/열람/읽음 처리.

## 데이터 위치 (Tier 1)

- `~/.hbrness/agentbus/registry.json` — 별칭 → pane 매핑
- `~/.hbrness/agentbus/inbox/<별칭>/*.json` — mailbox 메시지
- `~/.hbrness/agentbus/inbox/<별칭>/.read` — 읽음 처리 마커

## 추후 확장 — 브로드캐스트

### 왜 별도 스킬인가

`/agent-send` 에 `--all` / `--group` 옵션을 얹는 대신 `/agent-broadcast` 로 분리할 예정. 이유:

- **실수 비용**: `--all` 오타·자동완성 사고로 의도치 않은 전체 전송이 발생할 수 있음. 별도 명령어면 의식적 선택을 강제.
- **1:1 hot path 보존**: 인자 파싱이 단일 별칭 / `--all` / `--group X` 가 섞이지 않고 깔끔하게 유지됨.
- **의미론 분리**: 회신 처리(reply-to-sender vs reply-all)를 브로드캐스트 스킬에서만 다룸.
- **사용 빈도**: 1:1 이 압도적이라 UX 상 두 명령이 분리되어 있는 게 자연스러움.

같은 디렉토리/lib.sh 를 공유하므로 코드 중복 우려는 없음.

### 추가 작업량 — 작음

핵심 인프라(레지스트리, direct vs mailbox 분기, inbox 포맷, lib.sh) 가 그대로 재사용됨. 추가로 필요한 것만 정리하면:

1. **그룹 정의**: `registry.json` 의 각 항목에 `groups: ["fe-team"]` 같은 옵션 필드 추가. 기본 1:1 로직에는 무영향.
2. **수신자 확장 헬퍼**: `lib.sh` 에 `ab_expand_recipients(target) → [pane1, pane2, ...]` 함수 하나. `--all` / `--group <name>` 를 파싱해 별칭 배열로 펼침.
3. **send 루프**: 펼친 수신자마다 기존 `ab_send` 호출. mailbox 경로일 때는 **동일 파일을 hardlink** (또는 복사) 해서 각 inbox 에 배포 — 같은 `id` 로 추적 가능.
4. **스킬 디렉토리**: `plugins/agentbus/skills/agent-broadcast/SKILL.common.md` 하나. 내부적으로 `scripts/broadcast.sh` 추가.
5. **확인 단계**: tty 에서 호출되면 "N명에게 전송할까요?" 프롬프트.

### 이미 깔아둔 자리

지금 1:1 작업에서 미래 브로드캐스트를 위해 미리 자리만 잡아둔 부분:

- **모든 메시지에 `id` 부여**: direct 경로도 short hex id 를 결과 JSON 에 포함. 나중에 브로드캐스트 회신을 같은 id 로 묶어 추적 가능.
- **inbox 스키마의 옵셔널 필드**: `broadcast_group: null`, `recipients: null` 자리가 이미 있음 (1:1 일 때는 항상 null). 스키마 호환성을 깨지 않고 채우기만 하면 됨.

### 결정 보류 — 회신 의미론

브로드캐스트로 받은 메시지에 회신할 때 두 가지 옵션:

- **reply-to-sender**: `/agent-send <발신자>` — 기본 1:1 흐름과 동일.
- **reply-all**: `/agent-broadcast --group <원래그룹>` — 그룹 전체에 회신.

어느 쪽을 디폴트로 할지는 실제 사용 패턴이 쌓인 뒤 결정 (지금 정하면 over-design 위험).
