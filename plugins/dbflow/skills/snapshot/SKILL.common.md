---
name: snapshot
description: "소스 DB → 샌드박스 DB 복제 (pg_dump | pg_restore, docker 컨테이너 내부). \"dbflow snapshot\", \"DB 복제\" 요청 시 사용."
argument-hint: [--fresh (기존 sandbox drop 후 재생성)]
tools: [file:read, file:write, file:edit]
effort: high
---

# dbflow:snapshot — 소스 DB → 샌드박스 DB 복제

당신은 E2E 환경 DB 복제 엔지니어입니다.

## 컨텍스트 로드

작업 전 아래 문서들을 Read 하세요:

- `.e2e/config.yml`
- `.e2e/state.json` (있으면)
- **Safety invariants**: [safety_invariants.md](../../safety_invariants.md)

## ★ Safety Invariants ★ — 절대 변경 금지

```
## ★ Safety Invariants — 절대 변경 금지 ★

1. **소스 DB 쓰기 금지 + source URL 실행 계약 (hardcode invariant 1)**:
   - pg_dump 만 source URL 사용:
       docker exec -i {container} pg_dump -h {source_host} -p {source_port} \
         -U {source_user} -d {source_db} -Fc
   - pg_restore / CREATE DATABASE / psql INSERT 등은 sandbox URL 만 사용:
       docker exec -i {container} pg_restore -h {sandbox_host} -p {sandbox_port} \
         -U {sandbox_user} -d {sandbox_name}
   - source.allowed_hosts 가 비어있으면 → connect 즉시 거부.
   - source URL 의 host 가 allowed_hosts 에 없으면 → connect 즉시 거부.

2. **샌드박스 DB 이름 검증 (hardcode invariant 2)**:
   - sandbox.name 이 'sandbox' 또는 'e2e' 문자열을 포함하지 않으면
     → snapshot 즉시 거부. DROP DATABASE / CREATE DATABASE 실행 X.
   - "sandbox.name '<name>' 이 'sandbox' 또는 'e2e' 를 포함하지 않습니다.
      config.yml 을 확인하세요." 안내 후 종료.

3. **--fresh 시 사용자 confirm 필수 (hardcode invariant 3 — XR-001)**:
   - --fresh = 기존 sandbox DB drop 후 재생성 + 새 pg_restore.
   - 기존 sandbox DB 가 존재하면 사용자 confirm 필수:
       "sandbox DB '<sandbox_name>' 을 drop 하고 새로 복제할까요? (yes/no)"
   - 사용자가 'yes' 이외의 응답 → 취소.
   - config.yml auto_confirm / --no-confirm / --yes / --force → 미구현 / 무시.
   - 자동화 예외: 현재 turn 에 사용자가 직접 snapshot --fresh 를 요청한 경우만.
```

## 동작

### 1. config.yml 로드

`.e2e/config.yml` Read. 부재 시 "dbflow:init 먼저 실행하세요" 안내 후 종료.

### 2. sandbox.name 검증 (invariant 2)

`config.sandbox.name` 에 `sandbox` 또는 `e2e` 문자열이 포함되는지 확인.

- 미포함 → **즉시 실행 거부**:

```
✗ 실행 거부: sandbox.name '<name>' 에 'sandbox' 또는 'e2e' 가 포함되어 있지 않습니다.
  .e2e/config.yml 의 sandbox.name 을 확인하고, 이름에 sandbox 또는 e2e 를 포함하세요.
  예: myapp_sandbox, myapp_e2e_test
```

### 3. source URL 검증 (invariant 1)

1. `config.source.env_file` 에서 `config.source.url_var` 로 source URL 읽기.
2. URL 의 host 추출.
3. `config.source.allowed_hosts` 가 비어있으면 → **즉시 거부**:

```
✗ 실행 거부: source.allowed_hosts 가 비어있습니다.
  .e2e/config.yml 의 source.allowed_hosts 에 source DB host 를 추가하세요.
  예: [localhost, 127.0.0.1, postgres, db]
```

4. source URL host 가 allowed_hosts 에 없으면 → **즉시 거부**:

```
✗ 실행 거부: source URL 의 host '<host>' 가 source.allowed_hosts 에 없습니다.
  허용된 host: <allowed_hosts 목록>
```

5. SQLAlchemy async URL 자동 변환: `postgresql+asyncpg://` → `postgresql://` (pg_dump 용).

### 4. docker container 결정

`config.docker.container` 가 `auto` 이면:

```bash
docker ps --filter "ancestor=postgres" --format "{{.Names}}" | head -1
```

첫 번째 postgres 컨테이너를 자동 선택. 없으면:

```
✗ 실행 중인 postgres 컨테이너를 찾을 수 없습니다.
  docker ps 로 컨테이너를 확인하거나, config.docker.container 에 컨테이너 이름을 명시하세요.
```

명시적 이름이면 그대로 사용.

### 5. sandbox 연결 정보 결정

`config.sandbox.connection` 이 null 이면: source URL 의 host/port/user 상속, DB 이름만 `sandbox.name` 으로.

`config.sandbox.connection` 이 명시되면: 해당 host/port/user 사용.

sandbox URL (restore용):
```
postgresql://<sandbox_user>:<sandbox_password>@<sandbox_host>:<sandbox_port>/<sandbox_name>
```

### 6. 기존 sandbox 존재 여부 확인

```bash
docker exec -i <container> psql -U <sandbox_user> -h <sandbox_host> \
  -p <sandbox_port> -lqt 2>/dev/null | grep -qw <sandbox_name>
```

- 존재 + `--fresh` 옵션 있음 → 7단계 (confirm + drop)
- 존재 + `--fresh` 옵션 없음 → 8단계로 건너뜀 (drop 없이 restore 시도. pg_restore create-or-error 주의 — 기존 sandbox 위에 pg_restore 는 충돌 가능. 사용자에게 `--fresh` 권장 안내)
- 미존재 → 8단계 (CREATE DATABASE)

### 7. --fresh: sandbox DROP (confirm 필수, invariant 3)

기존 sandbox 가 있으면 사용자에게 confirm:

```
⚠ sandbox DB '<sandbox_name>' 이 이미 존재합니다.
  --fresh: 기존 sandbox 를 drop 하고 새로 복제합니다. 데이터가 모두 삭제됩니다.

정말로 진행할까요? (yes/no):
```

`yes` 이외 응답 → 취소:

```
취소되었습니다. sandbox DB 는 변경되지 않았습니다.
```

confirm 통과 후 drop:

```bash
docker exec -i <container> psql -U <sandbox_user> -h <sandbox_host> \
  -p <sandbox_port> -c "DROP DATABASE IF EXISTS \"<sandbox_name>\""
```

### 8. sandbox DB 생성 (없을 때 또는 --fresh drop 후)

```bash
docker exec -i <container> psql -U <sandbox_user> -h <sandbox_host> \
  -p <sandbox_port> -c "CREATE DATABASE \"<sandbox_name>\" OWNER \"<sandbox_owner>\""
```

### 9. extensions 적용

`config.sandbox.extensions` 목록이 비어있지 않으면:

```bash
docker exec -i <container> psql -U <sandbox_user> -h <sandbox_host> \
  -p <sandbox_port> -d <sandbox_name> \
  -c "CREATE EXTENSION IF NOT EXISTS \"<ext>\""
```

각 extension 에 대해 실행.

### 10. pg_dump | pg_restore (파이프)

**source = pg_dump 만. sandbox = pg_restore 만. (invariant 1)**

```bash
docker exec -i <container> pg_dump \
  -h <source_host> -p <source_port> -U <source_user> -d <source_db> -Fc \
  | docker exec -i <container> pg_restore \
    -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> \
    -d <sandbox_name> --no-owner --role=<sandbox_owner>
```

- 오류 발생 시 stderr 출력 + "snapshot 실패" 안내

옵션: `.e2e/snapshots/<ISO8601_TS>.dump` 에 dump 파일 보존 (config 에 dump_dir 가 지정된 경우).

### 11. state.json 업데이트

```json
{
  "last_snapshot_at": "<ISO8601 타임스탬프>",
  "last_snapshot_sha": "<source_url의 짧은 해시 또는 생략>"
}
```

### 12. 완료 출력

```
✓ snapshot 완료

  source → sandbox:
    source : <source_host>:<source_port>/<source_db>
    sandbox: <sandbox_host>:<sandbox_port>/<sandbox_name>
    컨테이너: <container>

  다음 단계:
    - 마이그레이션: dbflow:migrate
    - API 서버 기동: dbflow:up
```

## 쓰기 범위

- sandbox DB: CREATE DATABASE / DROP DATABASE (sandbox URL 만, source X)
- `.e2e/state.json`: last_snapshot_at, last_snapshot_sha 갱신
- `.e2e/snapshots/<TS>.dump`: 선택적 dump 파일 보존

## 품질 자가 점검

- [ ] pg_dump 에 source URL 사용, pg_restore 에 sandbox URL 사용 (source write 절대 X)
- [ ] source.allowed_hosts 비어있으면 즉시 거부
- [ ] sandbox.name 에 sandbox/e2e 포함 검증 선행
- [ ] --fresh 시 사용자 confirm 필수 (config/flag 로 우회 X)
- [ ] SQLAlchemy async URL 자동 변환 (postgresql+asyncpg:// → postgresql://)
- [ ] sandbox.connection 명시 시 해당 연결 정보 사용
- [ ] docker exec -i 로 컨테이너 내부 실행 (host 클라이언트 사용 X)
