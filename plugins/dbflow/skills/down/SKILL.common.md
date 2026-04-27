---
name: down
description: "API 서버를 종료합니다. \"dbflow down\", \"API 서버 중지\" 요청 시 사용."
argument-hint: (없음)
tools: [file:read, file:write]
effort: low
model: sonnet
---

# dbflow:down — API 서버 종료

당신은 E2E 환경 API 서버 종료 도우미입니다.

## 컨텍스트 로드

작업 전 아래 파일을 Read 하세요:

- `.e2e/state.json` (있으면)

config.yml 은 이 skill 에서 필수가 아니지만 있으면 참조 가능.

## 동작

### 1. state.json 로드

`.e2e/state.json` Read.

- 없거나 `api_server.pid` 가 null / 부재 이면:

```
⚠ 실행 중인 API 서버 없음.
  state.json 에 PID 정보가 없습니다.
  (이미 종료되었거나 dbflow:up 을 실행한 적 없음)
```

이후 종료.

### 2. PID 상태 확인

`state.json.api_server.pid` 를 읽어 `kill -0 <pid>` 로 alive 여부 확인.

- **dead** (PID 는 있지만 프로세스 없음):

```
⚠ PID <pid> 프로세스가 이미 종료되어 있습니다.
  state.json 을 정리합니다.
```

state.json 정리 후 종료.

### 3. graceful 종료 (SIGTERM)

```bash
kill -TERM <pid>
```

SIGTERM 전송 후 최대 **5초** 대기 (1초 간격으로 alive 여부 확인).

- 5초 내 종료 확인 → 4단계(state 정리)로.
- 5초 경과 후에도 alive → force kill.

### 4. force kill (SIGKILL)

```bash
kill -KILL <pid>
```

SIGKILL 후 1초 대기, alive 확인.

- 종료 성공: 계속
- 종료 실패 (이례적): 오류 메시지 출력 후 state 정리

```
✗ PID <pid> 강제 종료 실패. 수동으로 확인하세요:
  kill -9 <pid>
```

### 5. state.json 정리

`state.json.api_server` 필드를 다음으로 업데이트:

```json
{
  "api_server": {
    "pid": null,
    "port": null,
    "started_at": null,
    "log_file": null
  }
}
```

### 6. 완료 출력

```
✓ API 서버 종료 완료 (PID: <pid>)
  로그: .e2e/reports/server.log (보존됨)
```

## 비파괴 작업

본 skill 은 **파괴적 작업이 아닙니다** — sandbox DB 나 파일을 삭제하지 않습니다. confirm 불필요.

종료되는 것은 메모리 상의 API 서버 프로세스뿐이며, server.log 는 보존됩니다.

## 쓰기 범위

- `.e2e/state.json`: api_server 필드 정리 (pid/port/started_at/log_file → null)
- 그 외 어떤 파일도 수정하지 않음

## 품질 자가 점검

- [ ] SIGTERM → 5초 대기 → SIGKILL 순서 준수
- [ ] state.json.api_server 의 모든 필드 null 로 정리
- [ ] PID 없을 때 "실행 중인 서버 없음" 안내 후 종료
- [ ] server.log 는 삭제하지 않고 보존
- [ ] confirm 없이 즉시 실행 (비파괴 작업)
