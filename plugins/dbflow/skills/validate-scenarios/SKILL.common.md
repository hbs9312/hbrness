---
name: validate-scenarios
description: ".e2e/scenarios/*.yml 의 무결성 + safety invariant 검증. \"시나리오 검증\", \"dbflow validate\" 요청 시 사용."
argument-hint:
tools: [file:read, search:grep, search:glob]
effort: high
disable-model-invocation: true
---

# dbflow:validate-scenarios — 시나리오 무결성 + 안전 검증

당신은 E2E 시나리오 검증 엔지니어입니다.

## 컨텍스트 로드

작업 전 아래 문서들을 Read 하세요:

- `.e2e/config.yml` — 없으면 "dbflow:init 먼저 실행하세요" 안내 후 종료
- `.e2e/scenarios/` 전체 `*.yml` — glob 으로 수집
- `.e2e/fixtures/` 전체 `*.sql` — 존재 여부 및 내용 확인
- `.e2e/state.json` — 있으면 읽기
- `openapi/openapi.yaml` — 있으면 읽기 (없으면 §D api_call_match 건너뜀)
- **Safety invariants**: [safety_invariants.md](../../safety_invariants.md)

## 입력

argument 가 없으면 `.e2e/scenarios/` 전체를 검증.
argument 가 있으면 `.e2e/scenarios/<argument>.yml` 만 검증.

## 검증 절차 — §A~§F 순서로 실행

각 §를 순서대로 실행. 한 §가 실패해도 후속 §는 계속 실행 (전체 결과를 한 번에 보고).

---

### §A — 소스 DB 쓰기 금지 (hardcode invariant 1)

**A-1. source.allowed_hosts 비어있음 → critical**

`config.yml` 의 `source.allowed_hosts` 가 null / 빈 리스트 / 누락:

```
[CRITICAL §A-1] source.allowed_hosts 가 비어 있습니다.
  소스 DB 쓰기 금지 invariant 를 보장하려면 allowed_hosts 에 source DB 의 host 를 명시하세요.
  예: allowed_hosts: [prod-db.internal]
```

**A-2. source URL host 가 allowed_hosts 에 없음 → critical**

`config.yml` 의 `source.url` 에서 host 부분 추출 후, `source.allowed_hosts` 목록과 대조.

- host 추출 실패 (URL 파싱 불가) → warning ("source.url 형식을 확인하세요")
- 추출된 host 가 allowed_hosts 에 없음 → critical

```
[CRITICAL §A-2] source URL 의 host '<host>' 이 source.allowed_hosts 에 없습니다.
  source.allowed_hosts: [<list>]
  source.url: <url>
```

**A-3. scenarios / fixtures SQL 에 source URL host 직접 등장 → warning (보조 lint)**

> 주: 이 lint 는 보조 검사. 실행 경로 계약(pg_dump 만 source URL)이 1차 보장 (XR-006).
> 시나리오 파일과 fixture SQL 에서 grep 으로 source host 문자열 탐색.

```
[WARNING §A-3] '<file>' 에 source URL host '<host>' 가 직접 등장합니다.
  scenarios / fixtures 는 sandbox URL 만 사용해야 합니다.
  (SKILL 본문 계약이 1차 보장 — 이 경고는 보조 lint 입니다)
```

---

### §B — 샌드박스 DB 이름 (hardcode invariant 2)

**B-1. sandbox.name 이 'sandbox' 또는 'e2e' 미포함 → critical**

`config.yml` 의 `sandbox.name` 값에서 'sandbox' 또는 'e2e' 문자열 포함 여부 확인 (대소문자 무관).

```
[CRITICAL §B-1] sandbox.name '<name>' 에 'sandbox' 또는 'e2e' 가 포함되어 있지 않습니다.
  destructive 명령(snapshot --fresh / reset / migrate --fresh) 이 이 DB 를 대상으로 하면 모두 거부됩니다.
  sandbox.name 을 예: 'sandbox', 'sandbox_dev', 'e2e_test' 등으로 변경하세요.
```

---

### §C — Confirm bypass 금지 (hardcode invariant 3 — XR-001)

**C-1. config 에 confirm.* 또는 auto_confirm 등 키 등장 → critical**

`config.yml` 전체에서 다음 패턴 grep:
- 키 이름: `auto_confirm`, `skip_confirm`, `confirm:`, `confirm_bypass`, `no_confirm`

등장 시:

```
[CRITICAL §C-1] config.yml 에 confirm 우회 키 '<key>' 가 있습니다.
  confirm bypass 는 config 또는 flag 로 설정 불가. SKILL 본문 rule 로만 강제합니다.
  해당 키를 제거하세요. (XR-001)
```

**C-2. SKILL 또는 명령 history 에 --no-confirm / --yes / --force flag → critical**

시나리오 YAML 의 `command:` 필드 또는 config 의 임의 command 필드에서 grep:
- `--no-confirm`, `--yes`, `--force`, `-y` (단독 flag)

등장 시:

```
[CRITICAL §C-2] '<file>' 에 confirm bypass flag '<flag>' 가 사용되었습니다.
  destructive 명령(snapshot/reset/migrate --fresh) 에 대한 confirm 우회는 금지입니다.
  자동화 예외 = "현재 turn 에 사용자가 직접 destructive 명령 요청" 만. (XR-001)
```

---

### §D — 시나리오 무결성

각 시나리오 YAML (`*.yml`) 에 대해 아래 검사를 실행.

**D-1. schema_version: 1 필수 → 위반 시 critical**

`schema_version` 필드가 없거나 1 이 아닌 값:

```
[CRITICAL §D-1] '<file>' — schema_version 이 없거나 1 이 아닙니다 (현재: <value>).
  현재 schema_version: 1 만 공식 지원합니다.
```

**D-2. name / steps 필수 → 누락 시 critical**

```
[CRITICAL §D-2] '<file>' — 필수 필드 'name' 또는 'steps' 가 없습니다.
```

**D-3. watch_tables 누락 → warning**

```
[WARNING §D-3] '<file>' — watch_tables 가 없습니다.
  db_diff assertion 이 있는 step 에서 테이블이 자동 infer 되지만, 명시 권장입니다.
```

**D-4. step.request.{method, path} + expect 필수 → 누락 시 critical**

각 step 에서:

```
[CRITICAL §D-4] '<file>' step '<step_name>' — request.method 또는 request.path 또는 expect 가 없습니다.
```

**D-5. scenario name 전역 유일 → 중복 시 critical**

모든 시나리오 YAML 의 `name` 필드를 수집 후 중복 확인:

```
[CRITICAL §D-5] 시나리오 name '<name>' 이 중복됩니다: <file1>, <file2>
  scenario name 은 전역 유일해야 합니다.
```

**D-6. step.request.path 가 openapi.yaml path 와 매칭 → 불일치 시 warning**

`openapi/openapi.yaml` 이 있는 경우에만 실행.
각 step 의 `request.path` 에서 path parameter 를 템플릿(`{id}` → `{id}` 로 정규화)으로 변환한 후 openapi.yaml 의 paths 키와 대조.

- 변수 보간이 포함된 path (`{steps.X.response.Y}`) 는 path parameter 로 추상화 후 대조.
- 일치하지 않으면:

```
[WARNING §D-6] '<file>' step '<step_name>' — request.path '<path>' 이 openapi.yaml 에 없습니다.
  openapi paths: <일부 목록>
```

**D-7. fixtures.sql_file 가 .e2e/fixtures/ 에 존재 → 미존재 시 critical**

시나리오 YAML 의 `fixtures.sql_file` 경로(`.e2e/fixtures/` 상대 기준으로 해석) 파일 존재 확인:

```
[CRITICAL §D-7] '<file>' — fixtures.sql_file '<sql_file>' 이 .e2e/fixtures/ 에 없습니다.
  fixture 파일을 해당 경로에 배치하거나 fixtures.sql_file 경로를 수정하세요.
```

**D-8. fixture SQL 이 BEGIN/COMMIT wrapper → 미사용 시 warning**

`.e2e/fixtures/*.sql` 파일에서 `BEGIN` / `COMMIT` 패턴 grep:

```
[WARNING §D-8] '<sql_file>' — BEGIN; ... COMMIT; 트랜잭션 wrapper 가 없습니다.
  fixture SQL 은 BEGIN/COMMIT 으로 감싸 idempotency 를 보장하는 것을 권장합니다.
```

**D-9. 변수 interpolation 이 `{steps.<name>.response.<path>}` 형식만 → 다른 형식 critical (XR-008)**

각 step 의 `request.path` / `request.body` / `request.headers` 에서 변수 참조 패턴 grep:
- 허용: `{steps.<name>.response.<path>}` 형식
- 금지: `${fixture.X}`, `{{table.X}}`, `$VAR`, `%(VAR)s` 등 다른 형식

```
[CRITICAL §D-9] '<file>' step '<step_name>' — 허용되지 않는 변수 보간 형식 '<value>' 가 사용되었습니다.
  허용 형식: {steps.<name>.response.<path>} 만. (XR-008)
```

**D-10. db_diff assertion 키 범위 외 → critical (XR-009)**

각 step 의 `expect.db_diff.<table>` 키를 확인. 허용 키:

```
inserted_count, inserted_min, inserted_max, inserted_match,
deleted_count, deleted_match,
modified_count, modified_match,
unchanged
```

허용 키 외 등장 시:

```
[CRITICAL §D-10] '<file>' step '<step_name>' 테이블 '<table>' — 알 수 없는 db_diff assertion 키: '<key>'.
  허용 키: inserted_count, inserted_min, inserted_max, inserted_match, deleted_count, deleted_match, modified_count, modified_match, unchanged. (XR-009)
```

**D-11. modified_match 의 값이 {from, to} 또는 scalar → 형식 위반 시 warning**

각 step 의 `expect.db_diff.<table>.modified_match` 값 구조 확인:
- dict 또는 list 형식: 각 컬럼 값이 scalar (after value) 또는 `{from: X, to: Y}` / `{from: X}` / `{to: Y}` 구조여야 함
- 그 외 구조(예: 중첩 리스트, 잘못된 키) 는 warning

```
[WARNING §D-11] '<file>' step '<step_name>' 테이블 '<table>' — modified_match 형식이 올바르지 않습니다.
  허용: scalar (after value) 또는 {from: X, to: Y} transition 구조.
```

---

### §E — Auth 정합성

**E-1. auth.login_as 가 config.auth.users 키와 매칭 → 미매칭 시 critical**

시나리오 top-level `auth.login_as` 및 각 step `auth.login_as` 값을 수집.
`config.yml` 의 `auth.users` 키 목록과 대조.

```
[CRITICAL §E-1] '<file>' (step: '<step_name>' 또는 top-level) — auth.login_as '<email>' 이 config.auth.users 에 없습니다.
  config.yml 의 auth.users 에 해당 사용자를 추가하거나, login_as 값을 수정하세요.
```

**E-2. bearer 시 login_endpoint / token_field 누락 → critical**

`config.yml` 의 `auth.strategy` 가 `bearer` 이면:
- `auth.login_endpoint` 존재 확인
- `auth.token_field` 존재 확인

```
[CRITICAL §E-2] config.auth.strategy 가 'bearer' 이나 login_endpoint 또는 token_field 가 없습니다.
  bearer 전략에는 login_endpoint / token_field 가 필수입니다.
```

**E-3. jwt_direct 시 jwt.{secret_env, payload_template} 누락 → critical**

`config.yml` 의 `auth.strategy` 가 `jwt_direct` 이면:
- `auth.jwt.secret_env` 존재 확인
- `auth.jwt.payload_template` 존재 확인

```
[CRITICAL §E-3] config.auth.strategy 가 'jwt_direct' 이나 auth.jwt.secret_env 또는 auth.jwt.payload_template 이 없습니다.
  jwt_direct 전략에는 jwt.secret_env / jwt.payload_template 이 필수입니다.
```

---

### §F — 보안 hygiene

**F-1. config 에 plaintext password → warning**

`config.yml` 에서 `password:` 키의 값이 비어있지 않은 문자열인 경우:

```
[WARNING §F-1] config.yml 에 평문 password 값이 있습니다.
  'password_env' 를 사용하여 환경변수로 주입하는 것을 권장합니다.
  (해당 키: '<key_path>')
```

**F-2. fixture SQL 에 plaintext hash/secret → info**

`.e2e/fixtures/*.sql` 에서 `password`, `secret`, `token`, `hash` 컬럼에 단따옴표로 감싼 비어있지 않은 값 등장:

```
[INFO §F-2] '<sql_file>' — fixture SQL 에 평문 secret/hash 값이 있을 수 있습니다 ('<column>').
  의도된 시드 데이터라면 무시해도 됩니다. 실제 운영 비밀값이면 제거하세요.
```

---

## 출력 형식

findings 를 severity 순 (critical → warning → info) 으로 정렬하여 stdout 출력:

```yaml
validate_scenarios:
  config: .e2e/config.yml
  scenarios_checked: <N>
  fixtures_checked: <N>
  openapi_checked: <true|false>
  findings:
    - severity: critical
      rule: §A-1
      message: "source.allowed_hosts 가 비어 있습니다."
      file: .e2e/config.yml
    - severity: warning
      rule: §D-3
      message: "watch_tables 가 없습니다."
      file: .e2e/scenarios/post_crud.yml
    # ...
  summary:
    critical: <N>
    warning: <N>
    info: <N>
    verdict: FAIL   # critical >= 1 이면 FAIL, 아니면 PASS
```

**verdict**:
- `FAIL` — critical 이 1건 이상
- `PASS` — critical 0건 (warning / info 는 PASS 에 영향 없음)

critical 이 있으면 마지막에 아래 안내 출력:

```
✗ 검증 실패 — critical <N> 건. dbflow:run 전에 반드시 수정하세요.
```

critical 이 없으면:

```
✓ 검증 통과 (<N> scenarios). warning <N> 건은 선택 개선 사항입니다.
```

## 쓰기 범위

- **읽기 전용** — 파일 수정 없음
- findings 는 stdout (세션 내 출력). 파일 저장 X

## 품질 자가 점검

- [ ] §A-1 source.allowed_hosts 빈 값 검출 동작
- [ ] §A-2 source URL host vs allowed_hosts 대조 동작
- [ ] §B-1 sandbox.name 패턴 검사 동작 ('sandbox'/'e2e' 미포함 시 critical)
- [ ] §C-1 config 내 confirm 우회 키 grep 동작
- [ ] §D-1 schema_version: 1 검사 동작
- [ ] §D-5 시나리오 name 전역 중복 검출 동작
- [ ] §D-7 fixtures.sql_file 존재 확인 동작
- [ ] §D-9 금지 보간 형식 검출 동작 (XR-008)
- [ ] §D-10 허용 외 db_diff assertion 키 검출 동작 (XR-009)
- [ ] §E-1 login_as vs config.auth.users 대조 동작
- [ ] §F-1 config 평문 password 감지 동작
- [ ] verdict: critical >= 1 → FAIL, 0 → PASS
