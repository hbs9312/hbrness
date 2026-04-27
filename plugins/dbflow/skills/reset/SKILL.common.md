---
name: reset
description: "샌드박스 DB drop + state.json 삭제 + snapshots 정리. \"dbflow 초기화\", \"샌드박스 삭제\" 요청 시 사용."
argument-hint: [--snapshots (snapshots 도 정리)]
tools: [file:read, file:write, file:edit]
effort: low
model: sonnet
---

# dbflow:reset — 샌드박스 환경 정리

당신은 E2E 환경 정리 도우미입니다.

## 컨텍스트 로드

작업 전 아래 문서들을 Read 하세요:

- `.e2e/config.yml`
- `.e2e/state.json` (있으면)
- **Safety invariants**: [safety_invariants.md](../../safety_invariants.md)

## ★ Safety Invariants ★ — 절대 변경 금지

```
## ★ Safety Invariants — 절대 변경 금지 ★

1. **샌드박스 DB 이름 검증 (hardcode invariant 2)**:
   sandbox.name 이 'sandbox' 또는 'e2e' 문자열을 포함하지 않으면
   → 즉시 실행 거부. DROP DATABASE 실행 X.
   → "sandbox.name '<name>' 이 'sandbox' 또는 'e2e' 를 포함하지 않습니다.
      config.yml 을 확인하세요." 안내 후 종료.

2. **사용자 confirm 필수 (hardcode invariant 3 — XR-001)**:
   reset 은 destructive 작업입니다. 항상 사용자에게 확인을 요청하세요:
   → "정말로 sandbox DB '<sandbox_name>' 을 삭제할까요? (yes/no)"
   → 사용자가 명시적으로 "yes" 라고 응답한 경우에만 진행합니다.

   우회 불가 경우 (모두 거부):
   - config.yml 의 auto_confirm / confirm.* 키 → 무시 (config 로 우회 X)
   - --no-confirm / --yes / --force flag → 미구현 (flag 자체 없음)
   - CI 파이프라인 / 자동화 스크립트 → 예외 미해당

   자동화 예외 (유일한 허용 예외):
   - "현재 turn 에 사용자가 직접 reset 명령을 요청한 경우" 만 confirm 생략 허용
   - 단, 이 예외에도 sandbox 이름 검증 (invariant 1) 은 항상 실행

3. **source DB 절대 미접촉 (hardcode invariant 1)**:
   본 skill 은 sandbox DB 만 drop 합니다.
   source DB 에는 어떤 명령도 (읽기 포함 DROP/TRUNCATE/SELECT) 실행하지 않습니다.
   sandbox URL 만 사용. source URL 은 접근 X.
```

## 동작

### 1. config.yml 로드

`.e2e/config.yml` Read. 부재 시 "dbflow:init 먼저 실행하세요" 안내 후 종료.

### 2. sandbox.name 검증 (invariant 2)

`config.sandbox.name` 에 `sandbox` 또는 `e2e` 문자열이 포함되는지 확인.

- 포함: 계속 진행
- 미포함: **즉시 실행 거부**

```
✗ 실행 거부: sandbox.name '<name>' 에 'sandbox' 또는 'e2e' 가 포함되어 있지 않습니다.
  .e2e/config.yml 의 sandbox.name 을 확인하고, 이름에 sandbox 또는 e2e 를 포함하세요.
  예: myapp_sandbox, myapp_e2e_test
```

### 3. 사용자 confirm 요청 (invariant 3)

sandbox.name 검증 통과 후 반드시 사용자에게 확인:

```
⚠ 경고: sandbox DB '<sandbox_name>' 을 drop 하고 state.json 을 삭제합니다.
  이 작업은 되돌릴 수 없습니다.

정말로 진행할까요? (yes/no):
```

사용자가 `yes` 이외의 응답(`no`, `n`, 빈 값, 기타) → **취소**:

```
취소되었습니다. sandbox DB 는 변경되지 않았습니다.
```

**자동화 예외**: 현재 turn 에서 사용자가 직접 reset 을 요청한 경우 (예: "dbflow reset 해줘", "샌드박스 삭제해줘") — confirm 질문 후 yes 응답을 받은 것과 동일하게 처리 가능. 단, sandbox 이름 검증은 이 경우에도 반드시 실행.

### 4. API 서버 확인

`state.json.api_server.pid` 가 있고 alive 상태이면:

```
⚠ API 서버 (PID: <pid>) 가 실행 중입니다.
  계속하려면 먼저 dbflow:down 을 실행하거나, 지금 종료할까요? (stop/cancel):
```

- `stop` 선택: `kill <pid>` 후 계속
- `cancel`: 취소

### 5. sandbox DB DROP

**sandbox 연결 정보만 사용. source 연결 정보 사용 X.**

sandbox 연결: `config.sandbox.connection` (null 이면 source 의 host/port/user 상속, DB 이름은 sandbox.name).

```bash
docker exec -i <container> psql -U <owner> -c "DROP DATABASE IF EXISTS \"<sandbox_name>\""
```

- `docker.container: auto` 이면 `docker ps` 로 실행 중인 postgres 컨테이너 탐지
- DROP 성공: 계속
- DROP 실패 (컨테이너 미실행 등): 에러 메시지 출력 후 state.json / snapshots 는 계속 정리

### 6. state.json 삭제

`.e2e/state.json` 삭제 (또는 `{}` 으로 초기화). 없으면 건너뜀.

### 7. snapshots 정리 (--snapshots 옵션)

`$ARGUMENTS` 에 `--snapshots` 가 있으면 `.e2e/snapshots/` 디렉토리 내 파일 전체 삭제 (디렉토리 자체는 유지).

없으면 건너뜀 (snapshots 보존).

### 8. 완료 출력

```
✓ reset 완료

삭제된 항목:
  - sandbox DB: <sandbox_name>    (dropped | not found)
  - .e2e/state.json               (삭제됨 | 없었음)
  - .e2e/snapshots/*              (정리됨 | --snapshots 미사용으로 보존)

다음 단계:
  dbflow:snapshot 으로 sandbox DB 를 새로 생성할 수 있습니다.
```

## 쓰기 범위

- sandbox DB: DROP DATABASE (sandbox URL 만, source X)
- `.e2e/state.json`: 삭제 또는 `{}` 초기화
- `.e2e/snapshots/*`: `--snapshots` 옵션 시만 정리

## 품질 자가 점검

- [ ] sandbox.name 검증이 항상 선행 실행됨 (자동화 예외에서도)
- [ ] 사용자 confirm 없이 DROP DATABASE 실행 X
- [ ] source DB 연결 정보로 어떤 명령도 실행하지 않음 (sandbox URL 만)
- [ ] `--no-confirm` / `--yes` / `--force` 같은 flag 미구현
- [ ] config.yml 의 `auto_confirm` / `confirm.*` 키 무시 (config 로 우회 X)
- [ ] `--snapshots` 옵션 없으면 `.e2e/snapshots/` 보존
