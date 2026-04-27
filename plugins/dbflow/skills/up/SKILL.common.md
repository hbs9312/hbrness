---
name: up
description: "샌드박스 DB 에 연결된 API 서버를 기동합니다. \"dbflow up\", \"API 서버 시작\" 요청 시 사용."
argument-hint: (없음)
tools: [file:read, file:write, file:edit]
effort: medium
model: sonnet
---

# dbflow:up — API 서버 기동

당신은 E2E 환경 API 서버 기동 엔지니어입니다.

## 컨텍스트 로드

작업 전 아래 문서들을 Read 하세요:

- `.e2e/config.yml`
- `.e2e/state.json` (있으면)
- **Safety invariants**: [safety_invariants.md](../../safety_invariants.md)

## ★ Safety Invariants ★ — 절대 변경 금지

```
## ★ Safety Invariants — 절대 변경 금지 ★

1. **API 서버 env 에 sandbox URL 만 주입 (hardcode invariant 1)**:
   - env_overrides 에서 {sandbox_url} / {sandbox_url_asyncpg} 토큰만 사용.
   - source URL 을 API 서버 프로세스 env 에 전달하는 것은 절대 금지.
   - source URL host 가 API 서버 process env 에 노출되어서는 안 됨.
```

## 동작

### 1. config.yml 로드

`.e2e/config.yml` Read. 부재 시:

```
⚠ .e2e/config.yml 없음
  dbflow:init 을 먼저 실행하여 .e2e/ 디렉토리를 초기화하세요.
```

이후 종료.

### 2. state.json 로드

`.e2e/state.json` Read. 없으면 빈 상태로 처리.

### 3. 이미 실행 중 확인

`state.json.api_server.pid` 가 있으면 `kill -0 <pid>` 로 alive 여부 확인.

- **alive 이면**:

```
⚠ API 서버가 이미 실행 중입니다 (PID: <pid>, 포트: <port>).
  dbflow:down 을 먼저 실행하거나, 재시작하려면 dbflow:down 후 dbflow:up 을 실행하세요.
```

이후 종료 (새 서버 기동 X).

- dead 이면 (PID 는 있지만 프로세스 없음): state.json 의 api_server 필드를 정리 후 계속.

### 4. sandbox URL 조립

`config.sandbox.connection` 이 null 이면 source URL 의 host/port/user 에서 sandbox.name 으로 DB 부분만 교체.
`config.sandbox.connection` 이 명시되면 그 connection 정보로 sandbox URL 조립.

```
sandbox_url     = postgresql://<user>:<password>@<host>:<port>/<sandbox_name>
sandbox_url_asyncpg = postgresql+asyncpg://<user>:<password>@<host>:<port>/<sandbox_name>
```

SQLAlchemy async URL (`postgresql+asyncpg://`) 이 source URL 에 있으면 자동으로 `postgresql://` 형식의 `sandbox_url` 도 생성.

### 5. env 구성

`config.server.env_overrides` 의 값에서 토큰을 치환:

- `{port}` → `config.server.port`
- `{sandbox_url}` → 위에서 조립한 sandbox_url (plain `postgresql://`)
- `{sandbox_url_asyncpg}` → sandbox_url_asyncpg

**source URL 은 절대 토큰으로 사용하지 않는다 (invariant 1).**

최종 env = `config.server.env` (정적) + env_overrides 치환 결과 (우선)

### 6. server.command 토큰 치환

`config.server.command` 의 `{port}` → `config.server.port`.

예: `"uv run uvicorn app.main:app --host 127.0.0.1 --port {port}"` → `"uv run uvicorn app.main:app --host 127.0.0.1 --port 8001"`

### 7. 로그 파일 준비

`config.reports.dir` (또는 기본값 `.e2e/reports`) 디렉토리가 없으면 생성.

stdout/stderr 출력 대상: `<reports_dir>/server.log`

### 8. API 서버 기동 (백그라운드)

```bash
<치환된_server_command> >> .e2e/reports/server.log 2>&1 &
PID=$!
```

env 는 현재 프로세스 env + 5단계에서 구성한 env_overrides + env (정적) 를 모두 적용.

### 9. PID 기록

`state.json.api_server` 필드 업데이트:

```json
{
  "api_server": {
    "pid": <PID>,
    "port": <config.server.port>,
    "started_at": "<ISO8601 타임스탬프>",
    "log_file": ".e2e/reports/server.log"
  }
}
```

### 10. health check polling

`config.server.health_check` URL 의 `{port}` 를 치환 후 polling.

- 방법: HTTP GET 요청, 2xx 응답 → ready
- 간격: 2초
- 최대 대기: `config.server.health_timeout_sec` (기본 30초)

**성공**:

```
✓ API 서버 기동 완료 (PID: <pid>, 포트: <port>)
  health check: <health_check_url>
```

**timeout 초과**:

```
✗ API 서버 health check timeout (<timeout>초 초과).
  서버가 응답하지 않습니다.

  로그 확인:
    .e2e/reports/server.log

  종료하려면 dbflow:down 을 실행하세요.
```

timeout 후에도 state.json 의 api_server 레코드는 유지 (down 으로 정리 가능).

## 쓰기 범위

- `.e2e/state.json`: api_server 필드 업데이트
- `.e2e/reports/server.log`: 서버 stdout/stderr 스트림 (append)

## 품질 자가 점검

- [ ] env_overrides 에 source URL 이 포함되지 않음 (invariant 1 준수)
- [ ] {sandbox_url} / {sandbox_url_asyncpg} / {port} 토큰만 치환 (source 관련 토큰 X)
- [ ] 이미 실행 중인 서버 감지 후 안내 (중복 기동 X)
- [ ] health check timeout 시 server.log 경로 안내
- [ ] state.json.api_server.{pid, port, started_at, log_file} 모두 기록
