# dbflow — E2E 샌드박스 DB 오케스트레이션

Phase 1 산출물(backflow / specflow 출력)을 **실제 DB · 실제 API 서버 위에서 검증**하는 인프라 플러그인.

새 코드를 생성하는 것이 아니라 환경을 오케스트레이션한다. specflow QA §5 → dbflow scenario YAML → run → DB delta 검증.

> **Origin**: velvetalk `~/development/velvetalk/backend/.claude/skills/e2e-db/` 를 hbrness 패턴(skill 분리 + Tier 0 + 4-tier storage)으로 포팅. config / scenario schema 는 velvetalk 원본과 **1:1 호환**.

---

## 지원 스택

- **Phase 1.5**: Postgres + Docker + Alembic 권장
- `migrate.command` 는 자유 문자열 → Django(`python manage.py migrate`) / Prisma(`npx prisma migrate deploy`) / Flyway(`flyway migrate`) 모두 호환
- Phase 2 에서 MySQL / SQLite / Mongo 어댑터 예정

---

## 11 Core Skills + validate-scenarios

| Skill | Sub-phase | 역할 |
|---|---|---|
| `dbflow:init` | 1.5.2 | `.e2e/` 스캐폴드 + `config.yml` template + `.gitignore` append |
| `dbflow:status` | 1.5.2 | sandbox 연결 / API server PID / last snapshot+migrate / watch 활성 출력 |
| `dbflow:reset` | 1.5.2 | sandbox DB drop + state.json 삭제 + (옵션) snapshots 정리 |
| `dbflow:snapshot` | 1.5.3 | `pg_dump source → pg_restore sandbox` (docker exec 안) |
| `dbflow:migrate` | 1.5.3 | `config.migrate.command` 실행 (env_override 적용) |
| `dbflow:up` | 1.5.3 | config.server.command 로 API server 기동, health_check 로 ready 검증 |
| `dbflow:down` | 1.5.3 | state.json 의 PID 종료 (graceful → force), state.json 정리 |
| `dbflow:watch` | 1.5.4 | 지정 테이블의 full row JSON + PK 집합을 watch-before.json 에 저장 |
| `dbflow:diff` | 1.5.4 | sandbox 현재 상태 vs watch-before.json 비교 (PK 기준 inserted/deleted/modified) |
| `dbflow:run` | 1.5.5 | scenario YAML 실행 → 각 step request/response/db_diff 검증 → JSON report |
| `dbflow:gen-scenarios` | 1.5.5 | specflow QA §5 표 + TS §3.2 fragment → `.e2e/scenarios/*.yml` 자동 생성 |
| `dbflow:validate-scenarios` | 1.5.6 | `.e2e/scenarios/*.yml` + config + fixtures 무결성 검증 (§A~§F) |

---

## 시작 (Scenario A — 신규 프로젝트)

```
1. dbflow:init          ← .e2e/ 스캐폴드
2. .e2e/config.yml 작성 ← allowed_hosts / sandbox.name / migrate.command
3. dbflow:snapshot      ← source → sandbox 첫 복제
4. dbflow:migrate       ← sandbox 에 마이그레이션
5. dbflow:up            ← API 서버 기동
6. specflow:generate-qa ← QA §5 E2E DB 시나리오 생성
7. dbflow:gen-scenarios ← .e2e/scenarios/*.yml 자동 생성
8. dbflow:run <scenario> ← 검증
```

자세한 사용법: `references/usage-guide.md`

---

## Safety Invariants (절대 변경 금지)

이 3가지는 **hardcode** — config 또는 flag 로 우회 불가.

1. **소스 DB 쓰기 금지** — `pg_dump wrapper 만 source URL 사용`. psql / pg_restore / migrate / fixture / API server 는 모두 sandbox URL 만.
2. **샌드박스 DB 이름 검증** — `sandbox.name` 이 반드시 `sandbox` 또는 `e2e` 문자열 포함. 위반 시 destructive 명령 전부 거부.
3. **파괴 작업 confirm** — `snapshot --fresh` / `reset` / `migrate --fresh` 는 SKILL 본문 rule 로 사용자 명시 confirm 필수. config / flag 우회 불가.

자세한 설명: `safety_invariants.md`

---

## Tier 0 저장소 (`.e2e/`)

```
.e2e/
├── config.yml        ← commit 대상 (source/docker/sandbox/migrate/server/auth/diff/reports)
├── state.json        ← gitignore (active sandbox 상태)
├── snapshots/        ← gitignore (watch-before.json)
├── fixtures/         ← commit 대상 (SQL seed files)
├── scenarios/        ← commit 대상 (*.yml)
├── cache/            ← gitignore
└── reports/          ← gitignore (JSON reports + server.log)
```

`dbflow:init` 이 `.gitignore` 에 `state.json / snapshots/ / cache/ / reports/` 를 자동 append (idempotent).

`AUTHORING.md` 의 **Tier 0** 정의에 따른다.

---

## velvetalk 마이그레이션 (Scenario B)

velvetalk `e2e-db/` 단일 SKILL → hbrness `dbflow` 11 SKILL 분리. **`.e2e/config.yml` 그대로 호환** (schema 동일). 기존 scenarios YAML / fixtures 그대로. 단일 명령 `/e2e-db init` 대신 `/dbflow:init` 사용.
