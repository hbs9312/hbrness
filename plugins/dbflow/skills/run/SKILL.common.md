---
name: run
description: "시나리오 YAML 실행 + 기대 DB delta 대조. \"dbflow run\", \"시나리오 실행\" 요청 시 사용."
argument-hint: [scenario_name]
tools: [file:read, file:write, file:edit, search:grep, search:glob]
effort: max
---

# dbflow:run — 시나리오 YAML 실행

당신은 E2E 시나리오 실행 엔지니어입니다.

## 컨텍스트 로드

작업 전 아래 문서들을 Read 하세요:

- `.e2e/config.yml` — 없으면 "dbflow:init 먼저 실행하세요" 안내 후 종료
- `.e2e/state.json` — 있으면 API 서버 상태 확인
- **Safety invariants**: [safety_invariants.md](../../safety_invariants.md)
- **Scenario schema**: [scenario-reference.md](../../references/scenario-reference.md)

## ★ Safety Invariants ★ — 절대 변경 금지

```
1. **sandbox URL 만 사용 (hardcode invariant 1)**:
   - fixture 적용 (psql -f), DB 스냅샷, 모든 psql 조회는 sandbox URL 만.
   - source URL 은 이 skill 에서 일절 사용 X.
   - source.allowed_hosts 가 비어있어도 run 은 source 에 접근하지 않는다 (source 검증 skip).

2. **샌드박스 DB 이름 검증 (hardcode invariant 2)**:
   - sandbox.name 이 'sandbox' 또는 'e2e' 문자열을 포함하지 않으면
     → 즉시 실행 거부.

3. **API 서버 sandbox 대상 (hardcode invariant)**:
   - 모든 HTTP 요청은 config.server.host + config.server.port 조합으로만.
   - 외부 URL / source host 로 요청 X.
```

## 입력

`argument` 로 받은 `scenario_name` → `.e2e/scenarios/<scenario_name>.yml` 로 파일 경로 결정.

argument 가 없으면:

```
✗ 시나리오 이름을 지정하세요.
  사용법: dbflow:run <scenario_name>
  예: dbflow:run post_crud
  사용 가능한 시나리오: .e2e/scenarios/ 디렉토리 확인
```

## 사전 조건 검증

### 1. config.yml 로드

`.e2e/config.yml` Read. 부재 시 "dbflow:init 먼저 실행하세요" 안내 후 종료.

### 2. sandbox.name 검증 (invariant 2)

`config.sandbox.name` 에 `sandbox` 또는 `e2e` 가 포함되는지 확인.

- 미포함 → **즉시 실행 거부**:

```
✗ 실행 거부: sandbox.name '<name>' 에 'sandbox' 또는 'e2e' 가 포함되어 있지 않습니다.
  .e2e/config.yml 의 sandbox.name 을 확인하세요.
```

### 3. API 서버 running 확인

`.e2e/state.json` 의 `api_server.pid` 가 존재하는지 확인.

없거나 state.json 가 없으면:

```
✗ API 서버가 실행 중이 아닙니다.
  먼저 dbflow:up 으로 API 서버를 기동하세요.
  (state.json 에 api_server.pid 가 없습니다)
```

### 4. 시나리오 파일 확인

`.e2e/scenarios/<scenario_name>.yml` Read. 부재 시:

```
✗ 시나리오 파일을 찾을 수 없습니다: .e2e/scenarios/<scenario_name>.yml
  dbflow:gen-scenarios 로 시나리오를 생성하거나, 직접 YAML 을 작성하세요.
```

`schema_version` 필드 확인: 존재하고 1이 아니면 경고 (실행은 계속):

```
⚠ schema_version: <ver> — 현재 schema_version: 1 만 공식 지원합니다.
```

`name` 과 `steps` 필드 필수. 누락 시:

```
✗ 시나리오 YAML 오류: 'name' 또는 'steps' 필드가 없습니다.
```

## docker container 결정

`config.docker.container` 가 `auto` 이면:

```bash
docker ps --filter "ancestor=postgres" --format "{{.Names}}" | head -1
```

없으면:

```
✗ 실행 중인 postgres 컨테이너를 찾을 수 없습니다.
  docker ps 로 컨테이너를 확인하거나, config.docker.container 에 컨테이너 이름을 명시하세요.
```

## 실행 흐름

### Step 1. fixtures.sql_file 적용

시나리오 YAML 에 `fixtures.sql_file` 이 존재하면:

경로는 시나리오 파일 기준 상대 경로. 절대 경로로 변환:
- 시나리오 파일이 `.e2e/scenarios/<name>.yml` 이면
- `../fixtures/some_seed.sql` → `.e2e/fixtures/some_seed.sql`

파일 존재 확인. 없으면:

```
✗ fixture 파일을 찾을 수 없습니다: <resolved_path>
  .e2e/fixtures/ 에 SQL fixture 파일을 배치하세요.
```

sandbox DB 에 fixture 적용 (sandbox URL 만 — invariant 1):

```bash
docker exec -i <container> psql \
  -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> -d <sandbox_name> \
  -f <fixture_path_inside_container>
```

컨테이너 내부 경로: host 경로를 docker cp 또는 volume mount 경로로 변환이 필요한 경우, 먼저 파일을 컨테이너에 복사:

```bash
docker cp <host_fixture_path> <container>:/tmp/<fixture_filename>
docker exec -i <container> psql \
  -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> -d <sandbox_name> \
  -f /tmp/<fixture_filename>
```

오류 발생 시 stderr 출력 + "fixture 적용 실패" 안내. 계속 진행하지 말고 종료.

### Step 2. auth token 생성

`config.auth` 와 시나리오 `auth` 블록 결합:

시나리오 `auth` 가 없으면: 인증 없음 (anonymous 실행).
시나리오 `auth.login_as` 가 있으면: 해당 email 로 token 생성.

token 생성 방법 (`config.auth.strategy`):

- **`bearer`**: `config.auth.login_endpoint` 에 POST 요청. `config.auth.users.<email>` 의 password 사용. 응답에서 `config.auth.token_field` 경로로 token 추출.
- **`jwt_direct`**: `config.auth.users.<email>` 에 미리 설정된 token 직접 사용.
- **`none`** 또는 미설정: 인증 헤더 없음.

token 이 있으면 모든 step 요청에 아래 헤더 추가:

```
<config.auth.header_name>: <config.auth.header_value_template (token 치환)>
```

예: `Authorization: Bearer <token>`

`config.auth.users` 에 `auth.login_as` email 이 없으면:

```
✗ 인증 오류: config.auth.users 에 '<email>' 이 없습니다.
  .e2e/config.yml 의 auth.users 에 해당 사용자를 추가하세요.
```

### Step 3. watch_tables 스냅샷 (before)

**자동 infer**: 모든 step 의 `expect.db_diff` 에 등장하는 테이블 이름을 수집.
시나리오 `watch_tables` 에 명시된 테이블 추가 (union).
`watch_tables: all` 이면 config.diff.exclude_tables 제외 전체 테이블.

최종 watch 대상 테이블 목록으로 **before 스냅샷** 캡처:

watch skill 메커니즘 동일:

```bash
# PK 컬럼 조회 (테이블별)
docker exec -i <container> psql \
  -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> -d <sandbox_name> \
  -Atc "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) WHERE i.indisprimary AND i.indrelid = '<table>'::regclass ORDER BY a.attnum"

# full row JSON (ignore_columns 미적용 — diff 에서만 적용)
docker exec -i <container> psql \
  -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> -d <sandbox_name> \
  -Atc "SELECT row_to_json(t) FROM <table> t ORDER BY <pk_col1>, <pk_col2>"
```

before 스냅샷을 메모리에 보관 (run 중 내부 사용). 파일로 저장:

`.e2e/snapshots/run-<scenario_name>-before.json`:

```json
{
  "captured_at": "<ISO8601>",
  "scenario": "<scenario_name>",
  "tables": {
    "<table>": {
      "pk_columns": ["<pk>"],
      "rows": [...]
    }
  }
}
```

### Step 4. steps 순차 실행

각 step 을 순서대로 실행. **한 step 이 실패해도 후속 step 계속 실행** (전체 결과를 한 번에 보고).

API base URL: `http://<config.server.host>:<config.server.port>`

#### 4-1. per-step auth override

step 에 `auth` 블록이 있으면:

- `auth.login_as: <email>` → 해당 email 로 token 생성 (Step 2 와 동일 방법)
- `auth: none` → 이 step 에서는 인증 헤더 제거

없으면: 시나리오 레벨 auth token 사용.

#### 4-2. 변수 interpolation

`request.path`, `request.body`, `request.headers`, `request.query` 내의 `{steps.<prev_step_name>.response.<json_path>}` 패턴을 치환:

- `<prev_step_name>`: 이전에 실행된 step 의 name
- `<json_path>`: 응답 JSON 의 dot-notation 경로 (예: `id`, `data.id`, `items.0.uuid`)
- 이전 step 이 존재하지 않거나 응답 경로가 없으면 → step 실패 + 오류 메시지 기록. 계속 진행.
- 다른 형식 (`${fixture.X}`, `{{table.X}}`) 은 치환하지 않고 오류 기록.

#### 4-3. HTTP 요청

```
<method> <base_url><path>
headers:
  Content-Type: application/json  (body 가 있을 때)
  <auth_header>: <token>          (인증 있을 때)
  <step.request.headers>          (merge)
query: <step.request.query>
body: <step.request.body (JSON)>
```

응답 캡처: status, headers, body (JSON 파싱 시도).

#### 4-4. 테이블 re-snapshot (after)

이 step 에서 `expect.db_diff` 에 등장하는 테이블들의 현재 상태를 다시 조회 (full row JSON, sandbox URL 만).

```bash
docker exec -i <container> psql \
  -h <sandbox_host> -p <sandbox_port> -U <sandbox_user> -d <sandbox_name> \
  -Atc "SELECT row_to_json(t) FROM <table> t ORDER BY <pk_col1>, <pk_col2>"
```

#### 4-5. expect 평가

각 assertion 을 평가하고 결과 기록. **모든 assertion 평가 후** step passed 여부 결정.

**status**:

- 정수: `response.status == status`
- 리스트: `response.status in status`
- 생략: `200 <= response.status < 300` (2xx)

**response_contains**:

응답 JSON 에서 `response_contains` 의 모든 key-value 부분 매칭.
중첩 dict 재귀 확인. list 는 order-insensitive 멤버십.
`response_equals` 와 동시 사용 금지 (둘 다 있으면 오류 기록).

**response_equals**:

응답 JSON 과 완전 동일 비교.

**db_diff** (테이블별):

before 스냅샷 vs after 스냅샷 PK 기준 비교:

1. `config.diff.ignore_columns` + `config.diff.per_table.<table>.ignore_columns` 적용: 비교 전 해당 컬럼 제거
2. PK 집합 계산:
   - inserted: after 에만 있는 PK
   - deleted: before 에만 있는 PK
   - modified: 양쪽에 있지만 (non-ignored) 컬럼값이 다른 PK
   - unchanged: 변화 없음

assertion 별 평가:

| Assertion | 평가 방법 |
|---|---|
| `inserted_count` | `len(inserted) == inserted_count` |
| `inserted_min` | `len(inserted) >= inserted_min` |
| `inserted_max` | `len(inserted) <= inserted_max` |
| `inserted_match` | dict: inserted 행 중 매칭되는 행 >= 1. list: 각 entry 당 매칭 행 >= 1 |
| `deleted_count` | `len(deleted) == deleted_count` |
| `deleted_match` | deleted 행 중 매칭 행 >= 1 |
| `modified_count` | `len(modified) == modified_count` |
| `modified_match` | dict 또는 list. 스칼라 값 = after row 와 비교. `{col: {from: X, to: Y}}` = before→after transition. `from` 만 = before 비교. `to` 만 = after 비교. |
| `unchanged` | `true` → inserted=0, deleted=0, modified=0 |

before 스냅샷에 해당 테이블이 없으면 (watch_tables 에 없었음):

```
⚠ '<table>' 이 before 스냅샷에 없습니다. db_diff 평가를 건너뜁니다.
```

step 결과 구조:

```json
{
  "name": "<step_name>",
  "request": {"method": "...", "path": "...", "body": {}},
  "response": {"status": 200, "body": {}},
  "db_diff": {
    "<table>": {
      "inserted": [...],
      "deleted": [...],
      "modified": [{"before": {...}, "after": {...}}]
    }
  },
  "checks": [
    {"name": "status == 201", "passed": true},
    {"name": "<table>.inserted_count == 1", "passed": true}
  ],
  "passed": true
}
```

### Step 5. 보고서 저장

`.e2e/reports/` 디렉토리가 없으면 생성.

`.e2e/reports/<scenario_name>-<TS>.json` Write:

```json
{
  "scenario": "<name>",
  "scenario_file": ".e2e/scenarios/<scenario_name>.yml",
  "started_at": "<ISO8601>",
  "finished_at": "<ISO8601>",
  "passed": false,
  "steps": [
    {
      "name": "...",
      "request": {...},
      "response": {"status": 200, "body": {...}},
      "db_diff": {"<table>": {"inserted": [], "deleted": [], "modified": []}},
      "checks": [{"name": "...", "passed": true}],
      "passed": true
    }
  ]
}
```

`passed`: 모든 step 이 passed 일 때만 `true`.

`<TS>`: UTC ISO8601 timestamp (`20260427T123456Z` 형식 — 파일명 안전).

### Step 6. state.json 갱신

`.e2e/state.json` 의 `last_run` 키를 업데이트:

```json
{
  "last_run": {
    "scenario": "<scenario_name>",
    "ran_at": "<ISO8601>",
    "passed": true,
    "report_path": ".e2e/reports/<scenario_name>-<TS>.json"
  }
}
```

기존 state.json 의 다른 키(`api_server`, `watch`, `last_snapshot_at` 등) 는 그대로 유지.

### Step 7. 최종 출력 + exit

**성공 시** (모든 step passed):

```
✓ 시나리오 통과: <scenario_name>

  steps: <N>개 모두 통과
  소요 시간: <Xs>
  보고서: .e2e/reports/<scenario_name>-<TS>.json
```

**실패 시** (하나라도 failed):

```
✗ 시나리오 실패: <scenario_name>

  통과: <N_pass>/<N_total> steps

  실패한 step:
    - <step_name>:
        <check_name>: expected <expected>, got <actual>
        ...

  보고서: .e2e/reports/<scenario_name>-<TS>.json
  다음 단계: 보고서를 확인하거나 dbflow:diff 로 DB 상태 점검
```

**비-0 exit code**: 하나라도 실패한 step 이 있으면 실패 표시. (실제 exit code 는 SKILL 특성상 출력으로 표현)

## 쓰기 범위

- `.e2e/snapshots/run-<scenario_name>-before.json`: before 스냅샷 (sandbox URL 만)
- `.e2e/reports/<scenario_name>-<TS>.json`: JSON 보고서
- `.e2e/state.json`: `last_run` 갱신

**절대 쓰기 금지**:
- source DB (pg_dump 전용 — 이 skill 에서 source URL 사용 X)
- 시나리오 YAML 파일
- config.yml

## 품질 자가 점검

- [ ] sandbox URL 만 사용 (fixture psql / 스냅샷 조회 / watch 모두 sandbox URL, source 접근 0)
- [ ] sandbox.name 에 sandbox/e2e 포함 검증 선행
- [ ] API 서버 running 확인 (state.json api_server.pid)
- [ ] 실패 step 이 있어도 후속 step 계속 실행 (전체 보고)
- [ ] `{steps.<name>.response.<path>}` 외 보간 문법 거부 (XR-008)
- [ ] db_diff: PK 기준 비교, ignore_columns 적용, modified_match {from,to} transition 지원 (XR-009)
