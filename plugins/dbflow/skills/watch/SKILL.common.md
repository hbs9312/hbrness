---
name: watch
description: "지정 테이블의 before 스냅샷을 저장합니다. diff 의 기준이 됩니다. \"dbflow watch\", \"테이블 스냅샷\" 요청 시 사용."
argument-hint: [<tables> 또는 all]
tools: [file:read, file:write]
effort: medium
---

# dbflow:watch — 테이블 before 스냅샷 저장

당신은 E2E 환경 DB 상태 캡처 엔지니어입니다.

## 컨텍스트 로드

작업 전 아래 파일들을 Read 하세요:

- `.e2e/config.yml` — 없으면 "dbflow:init 먼저 실행하세요" 안내 후 종료
- `.e2e/state.json` — 있으면 기존 watch 메타 확인

## ★ Safety Invariants ★ — 절대 변경 금지

```
1. **sandbox URL 만 사용 (hardcode invariant 1)**:
   - psql 조회는 반드시 sandbox URL 만 사용. source URL 절대 사용 X.

2. **샌드박스 DB 이름 검증 (hardcode invariant 2)**:
   - sandbox.name 이 'sandbox' 또는 'e2e' 문자열을 포함하지 않으면
     → 즉시 실행 거부.
```

## 입력 파싱

argument 로 받은 테이블 목록:

- comma 또는 space 구분 목록: 해당 테이블만 스냅샷
- `all` 또는 argument 없음: config.diff.exclude_tables 를 제외한 **모든 테이블** 스냅샷

`all` 사용 시 전체 테이블 목록 조회:

```bash
docker exec -i <container> psql \
  -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> -d <sandbox_name> \
  -Atc "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
```

조회 결과에서 `config.diff.exclude_tables` 에 있는 테이블 제거.

## 동작

### 1. config.yml 로드

`.e2e/config.yml` Read. 부재 시 안내 후 종료.

### 2. sandbox.name 검증 (invariant 2)

`config.sandbox.name` 에 `sandbox` 또는 `e2e` 가 포함되는지 확인.

- 미포함 → **즉시 실행 거부**:

```
✗ 실행 거부: sandbox.name '<name>' 에 'sandbox' 또는 'e2e' 가 포함되어 있지 않습니다.
  .e2e/config.yml 의 sandbox.name 을 확인하세요.
```

### 3. docker container 결정

`config.docker.container` 가 `auto` 이면:

```bash
docker ps --filter "ancestor=postgres" --format "{{.Names}}" | head -1
```

없으면:

```
✗ 실행 중인 postgres 컨테이너를 찾을 수 없습니다.
  docker ps 로 컨테이너를 확인하거나, config.docker.container 에 컨테이너 이름을 명시하세요.
```

### 4. 기존 watch 확인 (confirm)

`.e2e/state.json` 의 `watch.captured_at` 가 존재하면 사용자 confirm:

```
⚠ 기존 watch 스냅샷이 있습니다.
  캡처 시각 : <watch.captured_at>
  테이블    : <watch.tables>

  덮어쓰면 이전 before 스냅샷이 사라집니다. 계속할까요? (yes/no):
```

`yes` 이외 응답 → 취소:

```
취소되었습니다. watch 스냅샷은 변경되지 않았습니다.
```

### 5. 대상 테이블 결정

argument 가 `all` 이거나 없으면: 3단계에서 조회한 전체 테이블 목록 사용 (exclude_tables 제외).

명시된 목록이면: 해당 목록 그대로 사용.

### 6. PK 컬럼 결정

각 테이블에 대해 primary key 컬럼 목록 조회:

```sql
SELECT a.attname
FROM pg_index i
JOIN pg_attribute a
  ON a.attrelid = i.indrelid
  AND a.attnum = ANY(i.indkey)
WHERE i.indisprimary
  AND i.indrelid = '<table>'::regclass
ORDER BY a.attnum
```

```bash
docker exec -i <container> psql \
  -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> -d <sandbox_name> \
  -Atc "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) WHERE i.indisprimary AND i.indrelid = '<table>'::regclass ORDER BY a.attnum"
```

PK 가 없는 테이블: `[]` 로 기록하고 경고 출력:

```
⚠ '<table>' 에 PK 가 없습니다. diff 에서 PK 기준 비교가 불가능합니다.
```

### 7. full row JSON 조회

각 테이블의 **전체 행** 을 JSON 으로 조회. **ignore_columns 는 이 시점에 적용하지 않음** — diff 에서만 적용.

PK 컬럼 기준 정렬:

```bash
docker exec -i <container> psql \
  -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> -d <sandbox_name> \
  -Atc "SELECT row_to_json(t) FROM <table> t ORDER BY <pk_col1>, <pk_col2>"
```

PK 가 없는 테이블: `ORDER BY 1` (첫 번째 컬럼 기준).

각 행은 `row_to_json` 이 반환한 JSON 문자열.

### 8. watch-before.json 저장

`.e2e/snapshots/` 디렉토리가 없으면 생성 (file:write 로 경로 포함 기록).

`.e2e/snapshots/watch-before.json` 에 아래 구조로 Write:

```json
{
  "captured_at": "<ISO8601 타임스탬프>",
  "tables": {
    "<table_name>": {
      "pk_columns": ["<pk_col1>", ...],
      "rows": [
        {"<col>": "<val>", ...},
        ...
      ]
    },
    ...
  }
}
```

`captured_at`: UTC ISO8601 (`2026-04-27T12:34:56Z` 형식).

### 9. state.json 갱신

`.e2e/state.json` 의 `watch` 키를 업데이트:

```json
{
  "watch": {
    "tables": ["<table1>", "<table2>", ...],
    "snapshot_path": ".e2e/snapshots/watch-before.json",
    "captured_at": "<ISO8601 타임스탬프>"
  }
}
```

기존 state.json 의 다른 키(`last_snapshot_at`, `api_server` 등) 는 그대로 유지.

### 10. 완료 출력

```
✓ watch 완료

  캡처 시각  : <captured_at>
  테이블     : [<table1>, <table2>, ...]
  행 수      : {table1: N행, table2: N행, ...}
  저장 경로  : .e2e/snapshots/watch-before.json

  다음 단계:
    - 변경 후 비교: dbflow:diff
```

## 쓰기 범위

- `.e2e/snapshots/watch-before.json`: before 스냅샷 (full row JSON) 저장
- `.e2e/state.json`: `watch.tables`, `watch.snapshot_path`, `watch.captured_at` 갱신

## 품질 자가 점검

- [ ] sandbox URL 만 사용 (source URL 절대 사용 X)
- [ ] sandbox.name 에 sandbox/e2e 포함 검증 선행
- [ ] 기존 watch 가 있으면 덮어쓰기 confirm 필수
- [ ] full row JSON 에 ignore_columns 미적용 (diff 에서만 적용)
- [ ] PK auto-detect (pg_index 쿼리) — PK 없으면 경고 + `[]`
- [ ] all 사용 시 exclude_tables 제외
- [ ] state.json 의 기존 다른 키 보존
