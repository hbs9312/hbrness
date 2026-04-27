---
name: migrate
description: "샌드박스 DB 에 마이그레이션을 적용합니다. \"dbflow migrate\", \"스키마 마이그레이션\" 요청 시 사용."
argument-hint: [--fresh (snapshot 재실행 후 마이그레이션)]
tools: [file:read, file:write, file:edit]
effort: medium
---

# dbflow:migrate — 마이그레이션 적용

당신은 E2E 환경 마이그레이션 엔지니어입니다.

## 컨텍스트 로드

작업 전 아래 문서들을 Read 하세요:

- `.e2e/config.yml`
- `.e2e/state.json` (있으면)
- **Safety invariants**: [safety_invariants.md](../../safety_invariants.md)

## ★ Safety Invariants ★ — 절대 변경 금지

```
## ★ Safety Invariants — 절대 변경 금지 ★

1. **migrate env 에 sandbox URL 만 주입 (hardcode invariant 1)**:
   - config.migrate.env_override 환경 변수에는 sandbox URL 만 설정.
   - source URL 을 마이그레이션 명령의 env 에 주입하는 것은 절대 금지.
   - source DB 에 마이그레이션을 실행하는 경로가 존재해서는 안 됨.

2. **샌드박스 DB 이름 검증 (hardcode invariant 2 — --fresh 시)**:
   - --fresh 옵션 사용 시: snapshot --fresh 와 동일한 이름 검증 적용.
   - sandbox.name 이 'sandbox' 또는 'e2e' 를 포함하지 않으면 → 거부.

3. **--fresh confirm (hardcode invariant 3 — XR-001)**:
   - --fresh 는 snapshot --fresh 를 먼저 호출 (sandbox drop 포함).
   - snapshot --fresh 의 confirm 절차가 포함됨 — migrate 에서 별도 추가 confirm 없음
     (snapshot --fresh 가 이미 confirm 을 수행).
   - config.yml auto_confirm / --no-confirm / --yes / --force → 미구현 / 무시.
```

## 동작

### 1. config.yml 로드

`.e2e/config.yml` Read. 부재 시 "dbflow:init 먼저 실행하세요" 안내 후 종료.

### 2. --fresh 처리

`$ARGUMENTS` 에 `--fresh` 가 있으면:

1. **sandbox.name 검증 (invariant 2)**: `sandbox.name` 에 `sandbox` 또는 `e2e` 포함 확인.
   - 미포함 → **즉시 거부** (reset 과 동일한 오류 메시지).

2. **dbflow:snapshot --fresh 호출**: snapshot skill 과 동일한 절차로 실행.
   - sandbox drop confirm 포함 (snapshot --fresh 의 invariant 3 절차 그대로).
   - snapshot 실패 시 migrate 도 중단.

3. snapshot 성공 후 이하 migrate 단계로 진행.

`--fresh` 없으면 2단계 건너뜀.

### 3. sandbox URL 조립

`config.sandbox.connection` 이 null 이면 source URL 의 host/port/user 에서 sandbox.name 으로 DB 부분만 교체.

`config.sandbox.connection` 이 명시되면 그 connection 정보로 sandbox URL 조립.

```
sandbox_url = postgresql://<user>:<password>@<host>:<port>/<sandbox_name>
```

SQLAlchemy async URL 이 source 에 있으면 plain `postgresql://` 형식으로 변환.

**source URL 은 sandbox URL 조립에만 참조하며, migrate 명령 env 에 절대 주입하지 않는다.**

### 4. migrate env 구성

```
env = config.migrate.env (정적 추가)
env[config.migrate.env_override] = sandbox_url   # ← sandbox URL 만 (invariant 1)
```

예: `DATABASE_URL = postgresql://postgres:password@localhost:5432/myapp_sandbox`

**source URL 은 이 env 에 절대 포함하지 않는다 (invariant 1).**

### 5. migrate.command 실행

```bash
<config.migrate.command>
```

- cwd: project root (git rev-parse --show-toplevel)
- env: 현재 프로세스 env + 4단계에서 구성한 migrate env (override)

`config.migrate.command` 는 자유 문자열 — stack 무관:
- `uv run alembic upgrade head`
- `python manage.py migrate --noinput`
- `npx prisma migrate deploy`
- `flyway migrate`

exit code 0 → 성공. 비-0 → 실패.

### 6. state.json 업데이트

성공 시:

```json
{
  "last_migrate_at": "<ISO8601 타임스탬프>",
  "last_migrate_status": "success"
}
```

실패 시:

```json
{
  "last_migrate_at": "<ISO8601 타임스탬프>",
  "last_migrate_status": "failed"
}
```

### 7. 결과 출력

**성공**:

```
✓ 마이그레이션 완료

  명령  : <config.migrate.command>
  sandbox: <sandbox_host>:<sandbox_port>/<sandbox_name>
  시각  : <ISO8601>

  다음 단계:
    - API 서버 기동: dbflow:up
```

**실패**:

```
✗ 마이그레이션 실패 (exit code: <code>)

  명령  : <config.migrate.command>
  sandbox: <sandbox_host>:<sandbox_port>/<sandbox_name>

  stderr:
  <stderr 출력>

  힌트:
  - sandbox 스키마 드리프트 의심 시: dbflow:migrate --fresh (snapshot 후 재시도)
  - 마이그레이션 명령 오류: .e2e/config.yml 의 migrate.command 를 확인하세요.
```

## 쓰기 범위

- `.e2e/state.json`: last_migrate_at, last_migrate_status 갱신
- sandbox DB: 마이그레이션 명령이 스키마를 변경 (sandbox URL 만)
- 그 외 파일 수정 없음

## 품질 자가 점검

- [ ] migrate env 에 sandbox URL 만 주입 (source URL 절대 X, invariant 1 준수)
- [ ] --fresh 시 snapshot --fresh 선행 호출 (sandbox 이름 검증 + confirm 포함)
- [ ] migrate.command 자유 실행 (stack 중립, cwd = project root)
- [ ] 실패 시 stderr + 힌트 출력 + state 갱신 (failed)
- [ ] state.json.last_migrate_at + last_migrate_status 항상 갱신
