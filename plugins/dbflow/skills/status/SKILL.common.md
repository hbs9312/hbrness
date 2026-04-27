---
name: status
description: "샌드박스 DB 연결, API 서버 PID, 마지막 snapshot/migrate, 활성 watch 등 현재 상태를 출력합니다. \"dbflow 상태\", \"e2e 상태\" 요청 시 사용."
argument-hint: (없음)
tools: [file:read, search:grep]
effort: low
---

# dbflow:status — 현재 상태 출력

당신은 E2E 환경 상태 확인 도우미입니다.

**본 skill 은 읽기 전용입니다. 어떤 파일도 수정하지 않습니다.**

## 컨텍스트 로드

작업 전 아래 두 파일을 Read 하세요:

- `.e2e/config.yml` — 없으면 "dbflow:init 먼저 실행하세요" 안내 후 종료
- `.e2e/state.json` — 없으면 "초기 상태 (snapshot 미실행)" 로 표시

## 동작

### 1. config.yml 로드

`.e2e/config.yml` 을 Read. 부재 시:

```
⚠ .e2e/config.yml 없음
  dbflow:init 을 먼저 실행하여 .e2e/ 디렉토리를 초기화하세요.
```

이후 종료 (state 확인 불가).

### 2. state.json 로드

`.e2e/state.json` 을 Read. 부재 시 "초기 상태" 로 모든 필드를 `(없음)` 표시.

### 3. 상태 항목 출력

아래 순서대로 출력:

#### 3.1 config 검증 요약

| 항목 | 값 | 상태 |
|---|---|---|
| `sandbox.name` | config 값 | `sandbox`/`e2e` 포함이면 ✓, 아니면 ⚠ WARNING |
| `source.allowed_hosts` | 목록 | 비어있으면 ⚠ WARNING: "allowed_hosts 가 비어있습니다. dbflow:snapshot 이 거부됩니다." |
| `docker.container` | 값 | 표시 |

#### 3.2 sandbox DB 연결

`sandbox.name` 과 `docker.container` 설정을 기반으로 sandbox DB 연결 가능 여부를 확인:

```bash
docker exec -i <container> psql -U <owner> -d <sandbox_name> -c "SELECT 1" 2>&1
```

- 성공: `✓ sandbox DB 연결 OK (<sandbox_name>)`
- 실패: `✗ sandbox DB 연결 실패: <에러 메시지>`
- `docker.container: auto` 인 경우 `docker ps` 로 실행 중인 postgres 컨테이너 자동 탐지

이 확인은 **read-only** (`SELECT 1` 만). 데이터 변경 없음.

#### 3.3 API 서버

`state.json.api_server` 에서 읽음:

| 항목 | 값 |
|---|---|
| PID | `api_server.pid` 또는 `(없음)` |
| 포트 | `api_server.port` 또는 `(없음)` |
| 상태 | PID 가 있으면 `kill -0 <pid>` 로 alive/dead 확인. 없으면 `(미실행)` |
| 시작 시각 | `api_server.started_at` 또는 `(없음)` |

#### 3.4 마지막 snapshot

`state.json.last_snapshot_at` + `state.json.last_snapshot_sha` 에서 읽음:

| 항목 | 값 |
|---|---|
| 시각 | `last_snapshot_at` 또는 `(없음)` |
| SHA | `last_snapshot_sha` 또는 `(없음)` |

#### 3.5 마지막 migrate

`state.json.last_migrate_at` 에서 읽음:

| 항목 | 값 |
|---|---|
| 시각 | `last_migrate_at` 또는 `(없음)` |

#### 3.6 활성 watch

`state.json.watch` 에서 읽음:

| 항목 | 값 |
|---|---|
| 감시 테이블 | `watch.tables` 또는 `(없음)` |
| 캡처 시각 | `watch.captured_at` 또는 `(없음)` |
| snapshot 경로 | `watch.snapshot_path` 또는 `(없음)` |

watch 가 없으면 "활성 watch 없음 (dbflow:watch <tables> 로 시작)" 안내.

### 4. 출력 예시

```
── dbflow status ──────────────────────────────────────

Config 검증:
  sandbox.name   : myapp_sandbox   ✓ (sandbox 포함)
  allowed_hosts  : [localhost, 127.0.0.1, postgres, db]  ✓
  docker.container: auto

Sandbox DB:
  연결           : ✓ OK (myapp_sandbox)

API 서버:
  PID            : 12345
  포트           : 8001
  상태           : ✓ alive
  시작 시각      : 2026-04-26T10:30:00

마지막 snapshot : 2026-04-26T10:28:00  SHA: abc1234
마지막 migrate  : 2026-04-26T10:29:00

활성 watch:
  테이블         : [posts, users]
  캡처 시각      : 2026-04-26T10:35:00
  snapshot 경로  : .e2e/snapshots/watch-before.json

───────────────────────────────────────────────────────
```

## 쓰기 X

본 skill 은 **어떤 파일도 수정하지 않습니다**. 읽기 + 출력만.
