---
name: init
description: ".e2e/ 디렉토리 스캐폴드 + config.yml template + .gitignore 자동 append. \"dbflow 초기화\", \"e2e 설정\" 요청 시 사용."
argument-hint: (없음)
tools: [file:read, file:write, file:edit]
effort: low
model: sonnet
---

# dbflow:init — .e2e/ 스캐폴드

당신은 E2E 테스트 환경 설정 엔지니어입니다.

## 컨텍스트 로드

작업 전 아래 두 문서를 Read 하세요:

- **플러그인 컨텍스트**: [dbflow.md](../../context/dbflow.md)
- **Safety invariants**: [safety_invariants.md](../../safety_invariants.md)

## 동작

### 1. 프로젝트 루트 결정

```bash
git rev-parse --show-toplevel
```

이후 모든 경로는 이 루트 기준 상대 경로.

### 2. `.e2e/` 디렉토리 생성 (없으면)

`.e2e/` 디렉토리가 존재하지 않으면 생성.

### 3. 하위 디렉토리 생성

아래 디렉토리 중 없는 것만 생성:

- `.e2e/scenarios/`
- `.e2e/fixtures/`
- `.e2e/snapshots/`
- `.e2e/cache/`
- `.e2e/reports/`

### 4. `.e2e/config.yml` 생성

**기존 config.yml 이 있으면 절대 덮어쓰지 않는다.** 있으면 건너뜀.

없을 때만 아래 template 을 그대로 생성:

```yaml
# .e2e/config.yml
# velvetalk e2e-db schema 1:1 호환 (XR-002)
# 모든 경로는 project root 상대.

source:
  env_file: .env                    # source DB URL 보관 파일
  url_var: DATABASE_URL             # env 변수명
  # ★ allowed_hosts 는 반드시 채워야 합니다 (비워두면 dbflow:snapshot 실행 거부).
  # source DB host 가 이 목록에 없으면 연결 거부 (hardcode invariant 1).
  allowed_hosts:
    - localhost
    - 127.0.0.1
    - postgres
    - db
  # URL 자체는 .env 에 (시크릿 분리). SQLAlchemy async URL 자동 변환.

docker:
  container: auto                   # auto = docker ps 의 첫 postgres:* 컨테이너. 또는 명시적 컨테이너 이름.
  # pg_dump / pg_restore / psql 모두 docker exec -i 로 컨테이너 내부 실행.

sandbox:
  # ★★ name 에는 반드시 'sandbox' 또는 'e2e' 문자열이 포함되어야 합니다 ★★
  # 포함되지 않으면 drop / snapshot --fresh / reset / migrate --fresh 실행 거부 (hardcode invariant 2).
  name: <project>_sandbox           # 예: myapp_sandbox, myapp_e2e_test
  extensions: []                    # CREATE EXTENSION IF NOT EXISTS 목록
  owner: postgres                   # sandbox DB 소유자
  connection: null                  # source 와 다른 서버에 sandbox 둘 때만. null 시 source 연결 정보 상속.
    # host: localhost
    # port: 5432
    # user: postgres
    # password_env: SANDBOX_DB_PASSWORD

migrate:
  command: "uv run alembic upgrade head"  # 자유 문자열 — Alembic / Django / Prisma / Flyway 모두 호환
  env_override: DATABASE_URL              # sandbox URL 로 override 할 env 변수명
  env: {}                                 # 추가 정적 env (예: PYTHONPATH: src)

server:
  command: "uv run uvicorn app.main:app --host 127.0.0.1 --port {port}"
  port: 8001
  health_check: "http://127.0.0.1:{port}/docs"
  health_timeout_sec: 30
  env_overrides:                          # {port}, {sandbox_url}, {sandbox_url_asyncpg} 토큰 사용 가능
    DATABASE_URL: "{sandbox_url}"
  env: {}

auth:
  strategy: bearer                        # bearer | jwt_direct | none
  header_name: Authorization
  header_value_template: "Bearer {token}"
  users:                                  # key 는 임의 라벨. step 의 auth.login_as 가 참조
    "testuser@example.com":
      password: "<plain>"                 # 또는 password_env: TEST_USER_PASSWORD
  # bearer 추가: login_endpoint / login_body_template / token_field
  # jwt_direct 추가: jwt.{secret_env, algorithm, access_ttl_seconds, payload_template}

diff:
  ignore_columns: [updated_at]            # 모든 테이블 공통 무시 컬럼
  per_table: {}                           # { posts: [edited_at] } 형식으로 테이블별 추가 무시
  exclude_tables: [alembic_version]       # watch all 시 제외할 테이블

reports:
  dir: .e2e/reports                       # JSON report + server.log 저장 위치

# (XR-001: confirm 정책은 이 config 에 없습니다. SKILL 본문 rule 로 강제됩니다.
#  auto_confirm / confirm.* 키를 추가해도 무시되며 dbflow:validate-scenarios §C 가 critical 오류 출력.)
```

### 5. `.e2e/state.json` 초기화

`.e2e/state.json` 이 없으면 빈 JSON `{}` 으로 생성.
있으면 건너뜀.

### 6. `.gitignore` idempotent append

프로젝트 루트 `.gitignore` 에 아래 4줄을 추가. **중복 추가하지 않는다** — 각 줄이 이미 존재하면 건너뜀.

```
.e2e/state.json
.e2e/snapshots/
.e2e/cache/
.e2e/reports/
```

`.gitignore` 가 없으면 새로 생성. 있으면 아래 처리:
1. 현재 내용 Read
2. 4개 항목 각각 존재 여부 확인
3. 없는 항목만 파일 끝에 append

### 7. 생성 결과 출력

작업 완료 후 아래 형식으로 결과 출력:

```
✓ .e2e/ 디렉토리 구조 생성 완료

생성된 항목:
  - .e2e/config.yml          (신규 생성 | 기존 보존)
  - .e2e/state.json          (신규 생성 | 기존 보존)
  - .e2e/scenarios/
  - .e2e/fixtures/
  - .e2e/snapshots/
  - .e2e/cache/
  - .e2e/reports/

.gitignore 에 추가된 항목:
  - .e2e/state.json          (추가 | 이미 존재)
  - .e2e/snapshots/          (추가 | 이미 존재)
  - .e2e/cache/              (추가 | 이미 존재)
  - .e2e/reports/            (추가 | 이미 존재)

다음 단계:
  1. .e2e/config.yml 편집: sandbox.name (sandbox/e2e 포함 필수), source.allowed_hosts 확인
  2. dbflow:snapshot 으로 source DB → sandbox DB 복제
```

## 멱등 보장

- 기존 `.e2e/` 가 있어도 빠진 항목만 추가 (전체 재생성 X)
- `config.yml` 기존 존재 시 덮어쓰기 절대 금지
- `.gitignore` append 는 중복 확인 후 없는 항목만

## 품질 자가 점검

- [ ] `.e2e/config.yml` template 이 velvetalk 원본 schema 와 1:1 호환 (source/docker/sandbox/migrate/server/auth/diff/reports 구조)
- [ ] `.gitignore` append 가 idempotent (중복 추가 X)
- [ ] 기존 `config.yml` 보존됨 (덮어쓰기 X)
- [ ] `sandbox.name` placeholder 에 "반드시 sandbox 또는 e2e 포함" 주석 포함
- [ ] `source.allowed_hosts` 비어있으면 안 된다는 주석 포함
- [ ] `config.yml` 에 `auto_confirm` / `confirm.*` 키 없음 (XR-001)
