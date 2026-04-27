# dbflow 프로젝트 설정 가이드

> 모든 dbflow skill 이 참조하는 프로젝트 설정. `.e2e/config.yml` 작성 가이드.
>
> velvetalk `e2e-db` 의 config schema 와 **1:1 호환** — velvetalk 프로젝트의 `.e2e/config.yml` 을 hbrness dbflow 에 그대로 사용 가능 (Scenario B 마이그레이션).

---

## `.e2e/config.yml` 전체 스키마

`dbflow:init` 이 아래 template 을 생성한다. 사용자는 `<...>` 자리를 채운다.

```yaml
# .e2e/config.yml
# dbflow — Phase 1.5 (Postgres + Docker + Alembic 권장)
# velvetalk e2e-db schema 와 1:1 호환

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
  # pg_dump / pg_restore / psql 모두 docker exec -i 로 컨테이너 내부 실행

sandbox:
  name: <project>_sandbox           # 반드시 'sandbox' 또는 'e2e' 포함 (hardcode invariant 2)
  extensions: []                    # CREATE EXTENSION IF NOT EXISTS
  owner: <sandbox connection user>
  connection: null                  # source 와 다른 서버에 sandbox 둘 때만. null 시 source host/port/user 상속
    # host: localhost
    # port: 5432
    # user: postgres
    # password_env: SANDBOX_DB_PASSWORD

migrate:
  command: "uv run alembic upgrade head"   # 자유 — Alembic / Django / Prisma / Flyway 호환
  env_override: DATABASE_URL                # sandbox URL 로 override 할 env 변수명
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

# (confirm 관련 키는 config 에 없음 — hardcode invariant 3, XR-001)
```

---

## 8 섹션 작성 가이드

### `source` — dev DB 클론 원본

- **`allowed_hosts` 가 핵심** (hardcode invariant 1). source URL 의 host 가 이 목록에 없으면 모든 snapshot 명령이 거부된다.
- `url_var` 는 `.env` 에 있는 source DB URL 의 변수명. URL 자체는 config 에 직접 쓰지 않는다 (시크릿 분리).
- `allowed_hosts` 기본값: `[localhost, 127.0.0.1, postgres, db]` — Docker Compose 내부 네트워크 호스트명 포함.

### `docker` — Postgres 컨테이너

- `container: auto` → `docker ps` 의 첫 번째 `postgres:*` 이미지 컨테이너를 자동 감지.
- 명시적 이름을 쓰려면: `container: my_postgres_container`.
- `pg_dump` / `pg_restore` / `psql` 모두 `docker exec -i` 로 컨테이너 내부에서 실행 (host client/server version mismatch 회피).

### `sandbox` — 대상 DB (이름 강제)

- **`sandbox.name` 이 'sandbox' 또는 'e2e' 포함** (hardcode invariant 2). 위반 시 destructive 명령 전부 거부.
  - 허용: `myproject_sandbox`, `myapp_e2e`, `e2e_sandbox_v2`
  - 거부: `myproject_db`, `test_database`, `dev_clone`
- `connection: null` 이면 source URL 의 host/port/user 를 상속. source 와 다른 서버에 sandbox 를 두려면 `connection` 섹션 명시.

### `migrate` — 스키마 마이그레이션 (자유 명령)

- `command` 는 자유 문자열 (stack 무관):
  - Alembic: `uv run alembic upgrade head`
  - Django: `python manage.py migrate --noinput`
  - Prisma: `npx prisma migrate deploy`
  - Flyway: `flyway migrate`
- `env_override` 에 명시한 env 변수에 sandbox URL 을 주입 후 command 실행.

### `server` — API 서버 기동

- `command` 의 `{port}`, `{sandbox_url}`, `{sandbox_url_asyncpg}` 는 런타임 토큰 — dbflow 가 자동 치환.
- `health_check` URL 이 200 을 반환할 때까지 `health_timeout_sec` 초 대기.
- 타임아웃 시 `.e2e/reports/server.log` 경로를 안내.

### `auth` — 인증 전략

3가지 strategy:
- `bearer` — `login_endpoint` 에 POST 해서 `token_field` 에서 토큰 추출. `users` 의 각 사용자별 자동 로그인.
- `jwt_direct` — `jwt.secret_env` + `jwt.payload_template` 으로 서버 없이 직접 JWT 생성.
- `none` — 인증 헤더 없이 모든 요청 전송.

`users` 의 key 가 시나리오의 `auth.login_as` 값과 매칭된다.

### `diff` — 테이블 비교 설정

- `ignore_columns` — 모든 테이블에 공통 적용. 타임스탬프 컬럼 (`updated_at`, `modified_at`) 추가 권장.
- `per_table` — 특정 테이블 추가 무시: `{ posts: [edited_at, view_count] }`.
- `exclude_tables` — `watch all` 시 제외할 테이블. 마이그레이션 추적 테이블 (`alembic_version`, `django_migrations`) 추가 권장.

### `reports` — 리포트 디렉토리

- `dir` 기본값: `.e2e/reports`. gitignore 대상.
- `dbflow:run` 이 `<name>-<TS>.json` 을 이 디렉토리에 생성.
- `dbflow:up` 이 `server.log` 를 이 디렉토리에 생성.

---

## stack 별 예시

### Alembic (기본)

```yaml
migrate:
  command: "uv run alembic upgrade head"
  env_override: DATABASE_URL
server:
  command: "uv run uvicorn app.main:app --host 127.0.0.1 --port {port}"
```

### Django

```yaml
migrate:
  command: "python manage.py migrate --noinput"
  env_override: DATABASE_URL
server:
  command: "python manage.py runserver 127.0.0.1:{port}"
```

### Prisma + Node

```yaml
migrate:
  command: "npx prisma migrate deploy"
  env_override: DATABASE_URL
server:
  command: "node dist/main.js"
```
