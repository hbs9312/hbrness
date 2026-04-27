# Phase 1.5 — dbflow 플러그인 설계

> **Generated**: 2026-04-27
> **Scope**: 신규 플러그인 `dbflow` (E2E 샌드박스 DB 오케스트레이션). velvetalk `e2e-db` skill (`~/development/velvetalk/backend/.claude/skills/e2e-db/`, Python CLI + 3 reference docs) 을 hbrness 패턴(skill 분리 + Tier 0 + 4-tier storage)으로 포팅
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.4
> **Tier**: Tier 0 (project-local, `.e2e/`)
> **Origin schema**: velvetalk reference 문서와 **1:1 호환** (config / scenario)
>
> **Revision (2026-04-27, Task 0 codex review — 10 findings, 4 critical · 5 warning · 1 info)**:
> - **XR-001 (critical)**: confirm 정책을 config 에서 제거. SKILL 본문 rule 로만 강제. `--no-confirm` flag 도 제거 (자동화 예외 = "현재 turn 에 사용자 명시 요청" 만)
> - **XR-002 (critical)**: config.yml schema 를 velvetalk 원본과 **1:1 호환** — `source / docker / sandbox / migrate / server / auth / diff / reports` 구조 유지. 내 임의 변경 (`source_db / sandbox_db / api_server`) 폐기
> - **XR-003 (critical)**: scenario YAML schema 를 velvetalk 원본 그대로 — `name / fixtures.sql_file / watch_tables / auth.login_as / steps[].request / steps[].expect.{status, response_contains, response_equals, db_diff}` + `{steps.X.response.Y}` interpolation
> - **XR-004 (critical)**: watch 가 **full row JSON** 을 `.e2e/snapshots/watch-before.json` 에 저장 + `diff.ignore_columns` 적용. state.json 에는 메타데이터만
> - **XR-005 (warning)**: skill 명수 표기 — "로드맵 9행 / 원본 11명령 / Phase 1.5 core skill 11개 / validate 포함 12 skill 파일" 로 분리, 전 문서 일관 적용
> - **XR-006 (warning)**: source write 금지 보장 = `pg_dump wrapper 만 source URL 사용, 그 외(psql/pg_restore/migrate/fixture/server)는 sandbox URL 만 받음` 실행 계약 hardcode. grep 은 보조 lint 한계 명시
> - **XR-007 (warning)**: Phase 1.5 config 는 `migrate.command` 만 노출 (자유 명령 — Alembic/Django/Prisma/Flyway 호환). `migration_tool.kind` enum 은 Phase 2 어댑터 hooks 로 별도 doc 분리
> - **XR-008 (warning)**: fixture 는 **SQL file 만** (`.e2e/fixtures/<scenario>_seed.sql`). `${fixture.X.Y}` 같은 가공 interpolation 폐기. 변수는 원본의 `{steps.X.response.Y}` 만
> - **XR-009 (warning)**: expected_delta DSL 폐기. 원본 `db_diff` 구조 (inserted_count / inserted_match / modified_match {from,to} / deleted_match / unchanged) 채택
> - **XR-010 (info)**: QA 표는 schema_version 없음, gen-scenarios 출력 YAML/생성 config 만 schema_version: 1

## 목표

Phase 1 (1)~(6) skill 출력물을 **실제 DB · 실제 API 서버 위에서 검증**하는 인프라. specflow QA 명세 §5 → dbflow scenario YAML → run → DB delta 검증. 새 코드 생성이 아니라 환경 오케스트레이션.

### 핵심 invariant (절대 변경 금지 — hardcode in SKILL prompt)

velvetalk e2e-db 의 안전 보장 그대로:

1. **소스 DB 쓰기 금지** — 실행 계약: `pg_dump wrapper 만 source URL 사용`. psql / pg_restore / migrate / fixture / API server / scenario 실행은 모두 **sandbox URL 만**. `source.allowed_hosts` 검증 (config 의 source URL host 가 whitelist 안에 있어야)
2. **샌드박스 DB 이름 검증** — `sandbox.name` 이 반드시 `sandbox` 또는 `e2e` 문자열 포함. 위반 시 모든 destructive 명령 거부 (drop / snapshot / reset / migrate --fresh)
3. **파괴 작업 confirm** — `snapshot --fresh` / `reset` / `migrate --fresh` 는 SKILL 본문 rule 로 사용자 명시 confirm 필수. **config 또는 flag 로 우회 불가** — confirm bypass 는 자동화 예외 ("현재 turn 에 사용자가 직접 destructive 명령 요청") 일 때만

이 3가지는 codex 가 가장 엄격하게 검사. SKILL prompt 명시 + `dbflow:validate-scenarios` (§A~§C) 검사.

### Non-goals

- Production DB 검증 — sandbox/e2e 만
- Node/Prisma/MySQL 등 다른 스택 — Phase 2 어댑터 (Phase 1.5 는 Postgres + Docker + Alembic 권장. 단 `migrate.command` 자유로 Django/Prisma 도 호환)
- 부하 테스트 — Phase 2
- Test data 생성 (faker) — `seed-data` skill 별개
- CI 통합 — Phase 3
- 시각화·대시보드 — JSON report 만
- 다중 샌드박스 동시 운영 — 단일 active sandbox + state.json
- 시나리오 임의 SQL/shell 실행 — fixture SQL 만 (DELETE-then-INSERT idempotent 패턴), step 안에서 임의 명령 X
- 다중 secret rotation — Phase 2
- velvetalk 외 stack 어댑터의 **선택지를 config 에 노출** — Phase 2 (현재 `migrate.command` 는 자유 문자열이라 stack 무관 동작 가능, 하지만 enum 등 stack 명시 X)

## 1. specflow 측 변경 — `§5 E2E DB 시나리오` (Phase 1.5.1)

`specflow:generate-qa` 출력에 §5 추가. **표는 source 기록만**, 실행 가능 YAML 은 `gen-scenarios` 가 생성. 표는 schema_version 없음.

### 섹션 포맷

```markdown
# 5. E2E DB 시나리오 (Phase 1.5)

| scenario_name | feature_ref | watch_tables | steps_summary | db_diff_summary | fixture_required |
|---|---|---|---|---|---|
| signup_persists_user | US-001, AC-003 | users | POST /api/v1/users | users.inserted_count: 1, users.inserted_match: { email matches } | (없음) |
| order_creates_payment | US-007, AC-014 | orders, payments | POST /api/v1/orders | orders +1 (status=pending), payments +1 (amount=cart.total) | order_seed (cart with 2 items) |
| webhook_idempotent | AC-021 | webhook_idempotency, payments | POST /webhooks/stripe ×2 | webhook_idempotency.inserted_count: 1 (2회째 unchanged), payments.unchanged: true | webhook_pending_payment |
```

### 섹션 규약

| 필드 | 필수 | 규칙 |
|---|---|---|
| `scenario_name` | required | snake_case + 문자열 (한글 허용 — 원본 `name` 과 매칭). 전역 유일 |
| `feature_ref` | required | US/AC/BR |
| `watch_tables` | required | comma 구분 또는 "all". 변경되는 테이블 + unchanged 단언 대상 |
| `steps_summary` | required | 자연어 — `gen-scenarios` 가 OpenAPI fragment + steps 패턴으로 변환 |
| `db_diff_summary` | required | 자연어 — `gen-scenarios` 가 원본 db_diff DSL 로 변환 |
| `fixture_required` | optional | fixture 파일명 (없으면 "(없음)"). cross-feature/edge state 만 |

### `specflow:generate-qa` 변경

- 프롬프트: "§5 E2E DB 시나리오 — DB 변화 있는 BR/AC 흡수. fixture 는 cross-feature/edge state 만 (in-feature 는 step chaining)"
- 자가 점검:
  - "§5 모든 행 watch_tables 명시"
  - "scenario_name 전역 유일 + snake_case 또는 한글"
  - "steps_summary 가 §3.2 OpenAPI fragment 의 path 와 매칭 가능"
  - "fixture_required 가 cross-feature 또는 edge state 일 때만 (in-feature 는 step chaining 사용 — 원본 reference 의 fixture 가이드 참조)"

### qa-rules 신규 룰 (warning grace)

(N = qa-rules 마지막 룰 +1; Phase 1.5.1 에서 부여)

```markdown
## E2E DB 시나리오 (warning — v1.x grace)
N. §5 E2E DB 시나리오 섹션 존재 — DB 변화 있는 BR/AC 가진 프로젝트만 의무
N+1. scenario_name 전역 유일 — 위반 시 warning
N+2. watch_tables 명시 — 누락 시 warning ("all 권장 안 함; 명시적 테이블 목록")
N+3. fixture_required 가 in-feature 동작을 fixture 로 우회 → warning ("step chaining 권장")
N+4. steps_summary 의 path 가 §3.2 fragment 의 canonical path 와 매칭 → 불일치 시 warning
```

## 2. dbflow plugin 구조

### 2.1 디렉토리 (12 SKILL 파일)

```
plugins/dbflow/
├── README.md
├── CONTRACTS.md
├── safety_invariants.md     # hardcode 3종 명시
├── context/
│   └── dbflow.md            # 사용자가 .e2e/config.yml 매핑 가이드
├── references/              # velvetalk reference 의 hbrness 적응판 (포팅 충실성 보장)
│   ├── config-reference.md
│   ├── scenario-reference.md
│   └── usage-guide.md
└── skills/
    ├── init/SKILL.common.md           # Phase 1.5.2
    ├── status/SKILL.common.md         # Phase 1.5.2
    ├── reset/SKILL.common.md          # Phase 1.5.2
    ├── up/SKILL.common.md             # Phase 1.5.3
    ├── down/SKILL.common.md           # Phase 1.5.3
    ├── snapshot/SKILL.common.md       # Phase 1.5.3
    ├── migrate/SKILL.common.md        # Phase 1.5.3
    ├── watch/SKILL.common.md          # Phase 1.5.4
    ├── diff/SKILL.common.md           # Phase 1.5.4
    ├── run/SKILL.common.md            # Phase 1.5.5
    ├── gen-scenarios/SKILL.common.md  # Phase 1.5.5
    └── validate-scenarios/SKILL.common.md  # Phase 1.5.6
```

**용어 (XR-005 명시 분리)**:
- **로드맵 §3.4 9행** — 표 행 단위 (up/down 한 행, reset/status 한 행)
- **velvetalk 원본 명령 11개** — init/snapshot/migrate/up/down/watch/diff/run/reset/status/gen-scenarios
- **Phase 1.5 core skill 11개** — 각 명령이 별도 SKILL 파일
- **Phase 1.5 SKILL 파일 12개** — core 11 + validate-scenarios 1 (Phase 1.5.6 신규)

### 2.2 hbrness plugin manifest

다른 plugin 들 (backflow / frontflow / specflow / ghflow / xreview / meeting-prep) 처럼 별도 `plugin.json` 없이 `plugins/dbflow/` 디렉토리만 추가. `build-plugin.py` 가 자동 인식.

### 2.3 Tier 0 — `.e2e/` 디렉토리 (원본 호환)

AUTHORING.md 에 이미 명시됨. 구조:

```
.e2e/
├── config.yml              # source/docker/sandbox/migrate/server/auth/diff/reports — velvetalk 원본 schema. commit 대상
├── state.json              # 활성 샌드박스 상태 (sandbox_status / api_server_pid / last_snapshot_at / last_migrate_at / watch 메타). gitignore
├── snapshots/
│   └── watch-before.json   # watch 시점 full row JSON. gitignore
├── fixtures/               # SQL fixture 파일 (commit 대상). 원본은 `.e2e/fixtures/<scenario>_seed.sql`
├── scenarios/
│   └── *.yml               # 시나리오 YAML (commit 대상)
├── cache/                  # gitignore (임시)
└── reports/                # gitignore. <scenario>-<TS>.json + server.log
```

`init` 이 `.gitignore` 에 자동 append:
```
.e2e/state.json
.e2e/snapshots/
.e2e/cache/
.e2e/reports/
```

`config.yml`, `fixtures/`, `scenarios/` 는 commit 대상.

## 3. config.yml schema (velvetalk 원본 1:1 호환 — XR-002)

`init` 이 생성. 사용자 수정. 모든 경로는 project root 상대.

```yaml
# .e2e/config.yml

source:
  env_file: .env                    # source DB URL 보관 파일
  url_var: DATABASE_URL             # env 변수명
  allowed_hosts:                    # source URL host 가 whitelist 에 있어야 (hardcode invariant 1)
    - localhost
    - 127.0.0.1
    - postgres
    - db
  # URL 자체는 .env 에 (시크릿 분리). SQLAlchemy async URL 자동 변환.

docker:
  container: auto                   # auto = docker ps 의 첫 postgres:* 컨테이너. 또는 명시적 이름.
  # pg_dump / pg_restore / psql 모두 docker exec -i 로 컨테이너 내부 실행 (host client/server version mismatch 회피)

sandbox:
  name: <project>_sandbox           # 반드시 'sandbox' 또는 'e2e' 포함 (hardcode invariant 2)
  extensions: []                    # CREATE EXTENSION IF NOT EXISTS
  owner: <sandbox connection user>
  connection: null                  # source 와 다른 서버에 sandbox 둘 때만. null 시 source URL 의 host/port/user 상속
    # host: localhost
    # port: 5432
    # user: postgres
    # password_env: SANDBOX_DB_PASSWORD

migrate:
  command: "uv run alembic upgrade head"   # 자유 — Alembic / Django / Prisma / Flyway 호환 (XR-007: stack enum 미노출)
  env_override: DATABASE_URL                # sandbox URL 로 override
  env: {}                                   # 추가 정적 env

server:
  command: "uv run uvicorn app.main:app --host 127.0.0.1 --port {port}"
  port: 8001
  health_check: "http://127.0.0.1:{port}/docs"
  health_timeout_sec: 30
  env_overrides:                            # {port}, {sandbox_url}, {sandbox_url_asyncpg} 토큰
    DATABASE_URL: "{sandbox_url}"
  env: {}

auth:
  strategy: bearer                          # bearer | jwt_direct | none
  header_name: Authorization
  header_value_template: "Bearer {token}"
  users:                                    # key 는 임의 라벨. step 의 auth.login_as 가 참조
    "testuser@example.com":
      password: "<plain>"
  # bearer 추가: login_endpoint / login_body_template / token_field
  # jwt_direct 추가: jwt.{secret_env, algorithm, access_ttl_seconds, payload_template}

diff:
  ignore_columns: [updated_at]              # 모든 테이블 공통 무시 컬럼
  per_table: {}                             # { posts: [edited_at] } 같은 추가 무시
  exclude_tables: [alembic_version]         # watch all 시 제외

reports:
  dir: .e2e/reports                         # JSON report + server.log

# (XR-001: confirm 정책 config 에 없음. SKILL 본문 rule 로 강제)
```

### 원본과의 호환

velvetalk 사용자가 `.e2e/config.yml` 을 hbrness dbflow 에 그대로 쓸 수 있어야 (Scenario B 마이그레이션). schema 변경 시 `schema_version: 1` (또는 v2 + converter — XR-002 권고).

## 4. scenario YAML schema (velvetalk 원본 1:1 호환 — XR-003)

`gen-scenarios` 출력 + `run` 입력. 원본 schema 그대로:

```yaml
# .e2e/scenarios/<scenario>.yml
schema_version: 1                # XR-010
name: "게시글 CRUD 플로우"        # 한글 허용 — 원본 패턴
description: |
  로그인 → 게시글 생성 → 목록 조회 → 삭제. 각 단계마다 DB 변화 검증.

fixtures:
  sql_file: ../fixtures/posts_crud_seed.sql   # optional. .e2e/fixtures/ 에 (XR-008: SQL file only)

watch_tables:                    # union of (steps[].expect.db_diff 의 모든 table) + 명시 추가
  - posts
  - users
# watch_tables: all              # 가능 (config.diff.exclude_tables 제외 모든 테이블)

auth:
  login_as: "testuser@example.com"   # config.auth.users 의 key

steps:
  - name: create
    request:
      method: POST
      path: /api/v1/posts
      body: { title: "안녕", content: "테스트" }
      # query: {}, headers: {}
    expect:
      status: 201
      response_contains: { title: "안녕" }
      db_diff:
        posts:
          inserted_count: 1
          inserted_match: { title: "안녕", content: "테스트" }
        users:
          unchanged: true

  - name: fetch
    request:
      method: GET
      path: "/api/v1/posts/{steps.create.response.id}"   # 변수 interpolation (XR-008)
    expect:
      status: 200
      db_diff:
        posts:
          unchanged: true        # reading shouldn't mutate

  - name: delete
    request:
      method: DELETE
      path: "/api/v1/posts/{steps.create.response.id}"
    auth:
      login_as: "admin@example.com"   # per-step auth override (XR-003)
    expect:
      status: 204
      db_diff:
        posts:
          deleted_count: 1
          deleted_match: { title: "안녕" }
```

### `db_diff` assertion DSL (원본 호환 — XR-009)

| Assertion | Type | Meaning |
|---|---|---|
| `inserted_count` | int | 정확한 insert 수 |
| `inserted_min` / `inserted_max` | int | 범위 |
| `inserted_match` | dict 또는 list of dicts | 적어도 한 행이 매칭. list 면 entry 별 1 매칭 |
| `deleted_count` | int | 정확한 delete 수 |
| `deleted_match` | dict | 적어도 한 deleted row 매칭 |
| `modified_count` | int | (ignore_columns 적용 후) 변경 행 수 |
| `modified_match` | dict 또는 list | 변경 행 패턴. `{col: {from, to}}` 로 transition 단언 |
| `unchanged` | bool | true = inserted=0, deleted=0, modified=0 shorthand |

PK 기준 비교. config.diff.ignore_columns + per_table 적용.

### 변수 interpolation (원본 — XR-008)

- `{steps.<step_name>.response.<json_path>}` — 이전 step 응답에서 값 추출. 다른 형식 (`${fixture.X}`, `{{table.last.col}}`) 폐기

### Step 의 expect 분기

- `expect.status` 생략 시 2xx 강제
- `response_contains` (부분 매칭) vs `response_equals` (전체) — 상호 배타

### Auth 흐름

1. config.auth.strategy 에 따라 token 생성
2. step 의 auth.login_as 가 config.auth.users 의 key 와 매칭
3. step 의 `auth: { login_as: <other> }` 또는 `auth: none` 으로 per-step override

## 5. 11 skill 책임 (간략)

각 skill 의 SKILL.common.md 는 sub-phase 1.5.2~1.5.6 에서 작성. 본 design 은 책임만.

### 5.1 `dbflow:init` (1.5.2)
`.e2e/` 스캐폴드 + `config.yml` template + `.gitignore` append. 멱등 (기존 보존).

### 5.2 `dbflow:status` (1.5.2)
sandbox 연결 / API server PID / last snapshot+migrate / watch 활성 출력. 쓰기 X.

### 5.3 `dbflow:reset` (1.5.2)
sandbox DB drop + state.json 삭제 + (옵션) snapshots 정리. **사용자 confirm 필수, sandbox 이름 검증**.

### 5.4 `dbflow:up` (1.5.3)
config.server.command 로 API server 기동. PID + port + log file 을 state.json 에. health_check 로 ready 검증. timeout 시 `.e2e/reports/server.log` 안내.

### 5.5 `dbflow:down` (1.5.3)
state.json 의 PID 종료 (graceful → force). state.json 정리.

### 5.6 `dbflow:snapshot` (1.5.3)
`pg_dump source → pg_restore sandbox` (docker exec 안). **source URL 은 pg_dump 만, restore/create-db 는 sandbox URL 만** (XR-006 hardcode). `--fresh` = 기존 sandbox drop 후 재생성 (sandbox 이름 검증 + confirm 필수). config.sandbox.extensions 적용.

### 5.7 `dbflow:migrate` (1.5.3)
`config.migrate.command` 실행 (env_override 적용). `--fresh` = snapshot 재실행 후 migrate. fresh 시 confirm.

### 5.8 `dbflow:watch <tables|all>` (1.5.4)
지정 테이블 (또는 config.diff.exclude_tables 제외 all) 의 **full row JSON** + PK 집합을 `.e2e/snapshots/watch-before.json` 에 저장 (XR-004). state.json 에 `watch.tables`, `watch.snapshot_path`, `watch.captured_at`. 기존 watch 가 있으면 confirm.

### 5.9 `dbflow:diff [<tables>]` (1.5.4)
sandbox 의 현재 상태 vs `watch-before.json` 비교. PK 기준 inserted/deleted/modified. config.diff.ignore_columns + per_table 적용. 출력: 표 + (옵션) `.e2e/reports/diff-<TS>.md`.

### 5.10 `dbflow:run <scenario>` (1.5.5)
1. config 검증 (allowed_hosts / sandbox name / API server up)
2. scenario YAML 로드 (schema_version 검증)
3. fixtures.sql_file 적용 (sandbox URL, idempotent SQL)
4. auth token 생성 (config.auth.strategy 에 따라)
5. watch_tables snapshot (auto-include from db_diff)
6. steps 순차 실행: request → response capture → re-snapshot → expect 평가
7. 보고서 `.e2e/reports/<name>-<TS>.json` (passed / steps[].checks)
8. 비-0 exit code 시 (옵션) chronicle future_notes 첨부 (Phase 1.5.6)

### 5.11 `dbflow:gen-scenarios` (1.5.5)
specflow QA §5 표 + TS §3.2 fragment 결합 → `.e2e/scenarios/<scenario_name>.yml` 자동 생성. 멱등 (기존 보존, 사용자 변경 시 confirm). steps 는 표의 steps_summary 에서 합성 — 보통 1~2 step. 다단계는 사용자가 수정.

### 5.12 `dbflow:validate-scenarios` (1.5.6 — 신규)
`.e2e/scenarios/*.yml` + config + fixtures 무결성 검증. invariant 위반 검사 (§7).

## 6. 동기화 메커니즘

```
specflow:generate-qa §5 (source of truth)
        │
        ▼
dbflow:gen-scenarios → .e2e/scenarios/*.yml
        │
        ▼
dbflow:run <scenario>
   ├─ snapshot watch_tables
   ├─ apply fixtures
   ├─ auth (config.auth)
   ├─ steps[].request → response capture
   ├─ re-snapshot
   ├─ expect.{status, response_contains, response_equals, db_diff} 평가
   └─ .e2e/reports/<name>-<TS>.json + exit code
        │
        ▼ (옵션, Phase 1.5.6)
ghflow:chronicle future_notes 첨부 (실패 시)
```

### Phase 1 skill 과의 연계 (Phase 1.5.6)

각 backflow SKILL Notes 에 dbflow 연계 한 줄 추가:
- `impl-schema` 후 → "새 migration 생겼습니다. `dbflow:migrate --fresh` 권장"
- `impl-error-codes` / `impl-services` / `impl-controllers` / `impl-file-upload` / `impl-webhook` 후 → "관련 시나리오 있으면 `dbflow:run` 추천"
- `validate-api` 후속 → 권고 시나리오 명시

## 7. dbflow:validate-scenarios 검사 룰 (Phase 1.5.6)

```yaml
입력:
  config: .e2e/config.yml
  scenarios_dir: .e2e/scenarios/
  fixtures_dir: .e2e/fixtures/
  state: .e2e/state.json (있으면)
  openapi: openapi/openapi.yaml (있으면 — Phase 1 (3) 산출)

§A — 소스 DB 쓰기 금지 (hardcode invariant 1):
  source_allowed_hosts:
    - source.allowed_hosts 가 비어있음 → critical
    - source URL 의 host 가 allowed_hosts 에 없음 → critical
  no_source_write_path:
    - SKILL prompt 에 명시: pg_dump 만 source URL 사용. 그 외 (psql/pg_restore/migrate/server/fixture) 모두 sandbox URL — 이는 SKILL 본문 검증으로 강제 (skill 자체가 source URL 을 destructive command 에 넘기지 않음)
    - **grep 기반 보조 lint**: scenarios/fixtures 의 SQL 안에 source URL host 가 직접 등장 → warning ("실행 경로 검증과 별개; SKILL 본문 계약이 1차 보장 — XR-006")

§B — 샌드박스 DB 이름 (hardcode invariant 2):
  sandbox_name_pattern:
    - sandbox.name 이 'sandbox' 또는 'e2e' 미포함 → critical (drop/snapshot/reset 거부)
  destructive_target:
    - destructive 명령(snapshot --fresh / reset / migrate --fresh) 이 sandbox 외 DB 를 target → critical (SKILL 본문에서 sandbox URL 만 받도록 강제됨)

§C — Confirm bypass 금지 (hardcode invariant 3 — XR-001):
  no_confirm_in_config:
    - .e2e/config.yml 에 `confirm.*` 또는 `auto_confirm` 등 키가 등장 → critical (config 로 invariant 우회 금지)
  no_force_flag:
    - SKILL 또는 명령 history 에 `--no-confirm` / `--yes` / `--force` 같은 flag 가 destructive 명령 (snapshot/reset/migrate --fresh) 에 사용 → critical
    - 자동화 예외 = "현재 turn 에 사용자가 직접 destructive 명령 요청" 만. SKILL prompt 에 이 예외 명시

§D — 시나리오 무결성:
  schema_version:
    - 모든 .yml 의 schema_version 이 1 (또는 명시적 v2) → 위반 시 critical
  required_top_fields:
    - name / steps 누락 → critical
    - watch_tables 누락 → warning (db_diff 에서 자동 inferred 가능하지만 명시 권장)
  step_required_fields:
    - 각 step 의 request.{method, path} + expect 필수 → 누락 시 critical
  scenario_name_unique:
    - .yml 들의 name 전역 유일 → 중복 시 critical
  api_call_match:
    - 각 step 의 request.path 가 openapi.yaml 의 canonical path 또는 path template (e.g. `/api/v1/posts/{id}`) 에 매칭 → 불일치 시 warning
  fixture_exists:
    - fixtures.sql_file 가 .e2e/fixtures/<X>.sql 로 존재 → 미존재 시 critical
  fixture_idempotent:
    - fixture SQL 이 BEGIN; ... COMMIT; 로 감싸짐 + DELETE-then-INSERT 패턴 → 미사용 시 warning
  step_interpolation_grammar:
    - request.path / body / headers 의 변수가 `{steps.<name>.response.<path>}` 형식 → 다른 형식 (예: `${fixture.X}`, `{{table.X}}`) 등장 → critical (XR-008)
  db_diff_assertion_grammar:
    - assertion 키가 [inserted_count, inserted_min, inserted_max, inserted_match, deleted_count, deleted_match, modified_count, modified_match, unchanged] 외 → critical (XR-009)
  modified_match_transition:
    - modified_match 의 column 값이 `{from: X, to: Y}` 또는 scalar (after value) → 형식 위반 시 warning

§E — Auth 정합성:
  auth_user_exists:
    - step.auth.login_as 또는 top-level auth.login_as 가 config.auth.users 의 key 와 매칭 → 미매칭 시 critical
  auth_strategy_required_fields:
    - bearer 시 login_endpoint / token_field 누락 → critical
    - jwt_direct 시 jwt.{secret_env, payload_template} 누락 → critical

§F — 보안 hygiene:
  no_plaintext_secret_in_config:
    - config 에 `password: "<plain>"` 같은 평문 secret 등장 → warning ("password_env 권장")
  no_plaintext_secret_in_fixture:
    - fixture SQL 에 `password = '...'` 같은 평문 hash/secret → info (의도된 시드일 수 있음)
```

## 8. 마이그레이션

### 8.1 Scenario A — 신규
1. `dbflow:init` 으로 `.e2e/` 스캐폴드
2. `config.yml` 사용자 작성 (allowed_hosts, sandbox.name with `sandbox`/`e2e`, migrate.command)
3. `dbflow:snapshot` 첫 복제
4. `dbflow:migrate`
5. `dbflow:up` API 서버 기동
6. `specflow:generate-qa` 후 `dbflow:gen-scenarios`
7. `dbflow:run`

### 8.2 Scenario B — velvetalk 마이그레이션
- velvetalk `e2e-db/` 단일 SKILL → hbrness `dbflow` 11 SKILL 분리
- **`.e2e/config.yml` 그대로 호환** (schema 동일, XR-002)
- **scenarios YAML 그대로 호환** (schema_version: 1, XR-010)
- 사용자가 `/e2e-db init` 대신 `/dbflow:init` 같은 분리 명령 사용
- 기존 fixtures 도 그대로

### 8.3 Scenario C — 기존 .e2e/ 없는 hbrness 프로젝트
1. `dbflow:init` 만 실행
2. config.yml 사용자 채움 (allowed_hosts 가 핵심)
3. 표준 흐름

### 8.4 Scenario D — 다른 stack (Django / Prisma)
config.migrate.command 만 변경:
- Django: `python manage.py migrate --noinput`
- Prisma: `npx prisma migrate deploy`
- Flyway: `flyway migrate`

server.command 도 stack 별 변경. 나머지 (snapshot/watch/diff/run) 는 stack 무관.

## 9. CONTRACTS.md 갱신

- `plugins/dbflow/CONTRACTS.md` 신규 (backflow / frontflow 패턴):
  - 실행 순서 (init → snapshot → migrate → up → run [/ watch / diff] → reset)
  - 12 skill 카드 (11 core + validate-scenarios)
  - 공통 레지스트리: `.e2e/state.json`, `.e2e/config.yml`, `.e2e/scenarios/`, `.e2e/fixtures/`, `.e2e/snapshots/watch-before.json`, `.e2e/reports/`
  - specflow 역매핑: `QA §5 → gen-scenarios`, `TS §3.2 → run / validate-scenarios`
- `plugins/specflow/skills/generate-qa/SKILL.common.md` — §5 추가 (Phase 1.5.1)
- `plugins/specflow/skills/generate-qa/template.md` — §5 섹션 (Phase 1.5.1)
- `plugins/specflow/skills/validate/rules/qa-rules.md` — 신규 룰 (Phase 1.5.1)
- `plugins/AUTHORING.md` — `dbflow (예정)` → `dbflow` 로 (Phase 1.5.0). references 디렉토리 추가 가이드
- `plugins/backflow/skills/{impl-schema, impl-services, validate-api, ...}/SKILL.common.md` — dbflow 연계 (Phase 1.5.6)
- `plugins/ghflow/skills/chronicle/SKILL.common.md` — 시나리오 실패 시 future_notes 첨부 (Phase 1.5.6)

## 10. Future work (Phase 1.5 외)

- 다른 DB stack (MySQL / SQLite / Mongo) 어댑터 — Phase 2
- 다른 마이그레이션 도구 enum 노출 — Phase 2 (`adapter_contract.md` 별도 doc)
- 비-Docker sandbox — Phase 2
- 다중 샌드박스 동시 운영 — Phase 2
- 시나리오 DSL 확장 (before/after sandboxed shell) — Phase 2
- CI 통합 (GitHub Actions templating) — Phase 3
- HTML report / 시각화 — Phase 2
- seed-data + dbflow 연동 — Phase 2
- 부하 시나리오 (validate-load 통합) — Phase 2
- Production read-replica 검증 모드 — Phase 2 (allowed_hosts + read-only enforcement)

## 11. 완료 기준 (Definition of Done)

### "ship"

- [ ] `plugins/dbflow/` 디렉토리 + 12 SKILL 파일 + CONTRACTS + safety_invariants + context + references (Phase 1.5.0~1.5.6)
- [ ] `specflow:generate-qa` §5 + qa-rules (Phase 1.5.1)
- [ ] config.yml schema **velvetalk 원본 1:1 호환**
- [ ] scenario YAML schema **velvetalk 원본 1:1 호환** + db_diff 풍부 DSL
- [ ] safety invariants 3종 hardcode (sandbox naming / pg_dump only / confirm — config·flag 우회 0)
- [ ] `dbflow:validate-scenarios` 룰 §A~§F 동작
- [ ] watch full row JSON + ignore_columns 적용
- [ ] backflow / ghflow 연계 (Phase 1.5.6)
- [ ] 최소 1개 실프로젝트 E2E (velvetalk 시뮬 또는 본 레포 — gen-scenarios → run → 시나리오 1개 성공)
- [ ] AUTHORING.md `dbflow (예정)` 표기 정리

### "stable"

- 2개 이상 프로젝트 (velvetalk + 1) 실사용
- velvetalk 시나리오 (실 e2e-db 의 시나리오) 그대로 통과
- safety invariant 위반 1건 이상 검출 (사용자 실수 catch)
- Scenario A/B/C/D 마이그레이션 각각 1회

## 12. Sub-phase 요약

| Sub-phase | 범위 | 추정 commits |
|---|---|---|
| **1.5.0** (현재) | 본 design + plugins/dbflow/ 디렉토리 + CONTRACTS skeleton + safety_invariants.md + context/dbflow.md + references/ stub + AUTHORING 갱신 | 1 |
| **1.5.1** | specflow:generate-qa §5 + template + qa-rules | 2 |
| **1.5.2** | dbflow:init / status / reset + safety_invariants 본문 | 2 |
| **1.5.3** | dbflow:up / down / snapshot / migrate | 3 |
| **1.5.4** | dbflow:watch / diff (full row JSON + ignore_columns) | 2 |
| **1.5.5** | dbflow:run / gen-scenarios | 3 |
| **1.5.6** | backflow / ghflow 훅 연계 + dbflow:validate-scenarios (§A~§F) | 2 |

총 **~15 commits**, 2~3주.

각 sub-phase 마다 codex 리뷰 + (필요 시) post-review fixup. Sonnet 가 SKILL 본문 작성, Opus 가 sub-phase wrap-up 결정. velvetalk reference 문서 (config-reference.md, scenario-reference.md, usage-guide.md) 는 hbrness `references/` 디렉토리에 적응 이식 — 1.5.0 에서 stub, 각 sub-phase 에서 본문 채움.
