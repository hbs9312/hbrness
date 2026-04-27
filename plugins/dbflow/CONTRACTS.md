# dbflow — Skill I/O Contracts

> **Scope**: 각 스킬이 어떤 입력을 읽고 어떤 출력을 어디에 쓰는지 명시한다. config.yml / state.json / scenarios / fixtures / snapshots / reports 의 읽기·쓰기 소유권을 명확히 한다.
> **Why this doc exists**: 새 스킬 추가 시 계약이 암묵적으로 번지면 구현이 "해석"에 의존하게 된다. 이 문서는 계약의 기준선이다.
> **Storage tier**: `plugins/AUTHORING.md` 의 4-tier 규약을 따른다. `.e2e/` 전체가 **Tier 0** (project-local).

---

## 실행 순서 (canonical)

```
init
 │
 ▼
snapshot            ← source → sandbox 첫 복제 (pg_dump only source URL)
 │
 ▼
migrate             ← config.migrate.command (sandbox URL only)
 │
 ▼
up                  ← API server 기동 (sandbox URL)
 │
 ├──▶ watch <tables> ─▶ diff      ← 수동 테이블 변화 검사
 │
 ▼
run <scenario>      ← 시나리오 실행 (watch + steps + db_diff 검증)
 │
 ▼
reset               ← sandbox drop (사용자 confirm 필수)
```

`up` / `down` 은 lifecycle. `gen-scenarios` 는 `run` 전 시나리오 자동 생성. `validate-scenarios` 는 사전 무결성 검증.

---

## 핵심 공통 레지스트리

| 파일 | 쓰는 스킬 | 읽는 스킬 | Tier | 비고 |
|---|---|---|---|---|
| `.e2e/config.yml` | init (template 생성) | 전 스킬 | Tier 0 | 커밋 대상. velvetalk 원본 schema 1:1 호환 |
| `.e2e/state.json` | snapshot, migrate, up, down, watch | status, run, reset, diff | Tier 0 | gitignore. sandbox_status / api_server_pid / last_snapshot_at / last_migrate_at / watch 메타 |
| `.e2e/scenarios/*.yml` | gen-scenarios | run, validate-scenarios | Tier 0 | 커밋 대상. schema_version: 1 |
| `.e2e/fixtures/*.sql` | (사용자 작성 / gen-scenarios 안내) | run (fixture 적용), validate-scenarios | Tier 0 | 커밋 대상. SQL only, DELETE-then-INSERT idempotent |
| `.e2e/snapshots/watch-before.json` | watch | diff, run | Tier 0 | gitignore. full row JSON. config.diff.ignore_columns 적용 후 저장 |
| `.e2e/reports/<name>-<TS>.json` | run | (사용자) | Tier 0 | gitignore. passed / steps[].checks |
| `.e2e/reports/server.log` | up | (사용자) | Tier 0 | gitignore. API server 기동 로그 |

---

## 스킬별 계약

### init

| 항목 | 내용 |
|---|---|
| **Purpose** | `.e2e/` 스캐폴드 + `config.yml` template + `.gitignore` append. 멱등 (기존 보존) |
| **Reads** | 프로젝트 루트 (pwd / git rev-parse --show-toplevel), 기존 `.e2e/` 여부 확인 |
| **Writes** | `.e2e/config.yml` (template), `.e2e/scenarios/`, `.e2e/fixtures/`, `.e2e/snapshots/`, `.e2e/cache/`, `.e2e/reports/`, `.gitignore` append |
| **Storage Tier** | Tier 0 |
| **Depends on** | — (가장 먼저) |
| **Notes** | 본문은 Phase 1.5.2 에서 작성. |

### status

| 항목 | 내용 |
|---|---|
| **Purpose** | sandbox 연결 / API server PID / last snapshot+migrate / watch 활성 출력. 쓰기 X |
| **Reads** | `.e2e/config.yml`, `.e2e/state.json` |
| **Writes** | — (읽기 전용) |
| **Storage Tier** | Tier 0 |
| **Depends on** | init |
| **Notes** | 본문은 Phase 1.5.2 에서 작성. |

### reset

| 항목 | 내용 |
|---|---|
| **Purpose** | sandbox DB drop + state.json 삭제 + (옵션) snapshots 정리. 사용자 confirm 필수 |
| **Reads** | `.e2e/config.yml`, `.e2e/state.json` |
| **Writes** | `.e2e/state.json` (삭제), `.e2e/snapshots/` (옵션 정리) |
| **Storage Tier** | Tier 0 |
| **Depends on** | init |
| **Notes** | 본문은 Phase 1.5.2 에서 작성. sandbox 이름 검증 필수 (hardcode invariant 2). confirm 필수 (invariant 3). |

### snapshot

| 항목 | 내용 |
|---|---|
| **Purpose** | `pg_dump source → pg_restore sandbox` (docker exec 안). source URL 은 pg_dump 만, restore 는 sandbox URL 만 |
| **Reads** | `.e2e/config.yml` (source / docker / sandbox 섹션) |
| **Writes** | `.e2e/state.json` (last_snapshot_at) |
| **Storage Tier** | Tier 0 |
| **Depends on** | init |
| **Notes** | 본문은 Phase 1.5.3 에서 작성. `--fresh` = 기존 sandbox drop 후 재생성 (sandbox 이름 검증 + confirm 필수). |

### migrate

| 항목 | 내용 |
|---|---|
| **Purpose** | `config.migrate.command` 실행 (env_override 적용). sandbox URL 만 |
| **Reads** | `.e2e/config.yml` (migrate 섹션) |
| **Writes** | `.e2e/state.json` (last_migrate_at) |
| **Storage Tier** | Tier 0 |
| **Depends on** | snapshot |
| **Notes** | 본문은 Phase 1.5.3 에서 작성. `--fresh` = snapshot 재실행 후 migrate. fresh 시 confirm. |

### up

| 항목 | 내용 |
|---|---|
| **Purpose** | config.server.command 로 API server 기동. PID + port + log file 을 state.json 에. health_check 로 ready 검증 |
| **Reads** | `.e2e/config.yml` (server 섹션) |
| **Writes** | `.e2e/state.json` (api_server_pid, api_server_port), `.e2e/reports/server.log` |
| **Storage Tier** | Tier 0 |
| **Depends on** | migrate |
| **Notes** | 본문은 Phase 1.5.3 에서 작성. health_timeout_sec 초과 시 server.log 경로 안내. |

### down

| 항목 | 내용 |
|---|---|
| **Purpose** | state.json 의 PID 종료 (graceful → force). state.json 정리 |
| **Reads** | `.e2e/state.json` (api_server_pid) |
| **Writes** | `.e2e/state.json` (pid/port 항목 삭제) |
| **Storage Tier** | Tier 0 |
| **Depends on** | up |
| **Notes** | 본문은 Phase 1.5.3 에서 작성. |

### watch

| 항목 | 내용 |
|---|---|
| **Purpose** | 지정 테이블(또는 all) 의 full row JSON + PK 집합을 watch-before.json 에 저장 |
| **Reads** | `.e2e/config.yml` (diff.ignore_columns, diff.exclude_tables), `.e2e/state.json` (기존 watch 여부) |
| **Writes** | `.e2e/snapshots/watch-before.json` (full row JSON), `.e2e/state.json` (watch 메타: tables, snapshot_path, captured_at) |
| **Storage Tier** | Tier 0 |
| **Depends on** | up |
| **Notes** | 본문은 Phase 1.5.4 에서 작성. 기존 watch 가 있으면 confirm. `all` 시 config.diff.exclude_tables 제외. |

### diff

| 항목 | 내용 |
|---|---|
| **Purpose** | sandbox 현재 상태 vs watch-before.json 비교. PK 기준 inserted/deleted/modified |
| **Reads** | `.e2e/config.yml` (diff 섹션), `.e2e/snapshots/watch-before.json`, `.e2e/state.json` (watch 메타) |
| **Writes** | `.e2e/reports/diff-<TS>.md` (옵션) |
| **Storage Tier** | Tier 0 |
| **Depends on** | watch |
| **Notes** | 본문은 Phase 1.5.4 에서 작성. config.diff.ignore_columns + per_table 적용. |

### run

| 항목 | 내용 |
|---|---|
| **Purpose** | scenario YAML 순차 실행 → 각 step request/response 캡처 → db_diff 검증 → JSON report |
| **Reads** | `.e2e/config.yml` (전 섹션), `.e2e/scenarios/<scenario>.yml`, `.e2e/fixtures/` (sql_file 있으면), `.e2e/state.json` (API server PID/port) |
| **Writes** | `.e2e/snapshots/watch-before.json` (auto-watch), `.e2e/reports/<name>-<TS>.json` |
| **Storage Tier** | Tier 0 |
| **Depends on** | up, (선택) gen-scenarios |
| **Notes** | 본문은 Phase 1.5.5 에서 작성. config 검증(allowed_hosts / sandbox name / API server) 선행. fixture idempotent 적용. |

### gen-scenarios

| 항목 | 내용 |
|---|---|
| **Purpose** | specflow QA §5 표 + TS §3.2 fragment → `.e2e/scenarios/<scenario_name>.yml` 자동 생성. 멱등 |
| **Reads** | `specs/QA/*` §5 E2E DB 시나리오 표, `specs/TS/*` §3.2 OpenAPI fragment, `.e2e/config.yml` (auth 섹션) |
| **Writes** | `.e2e/scenarios/<scenario_name>.yml` |
| **Storage Tier** | Tier 0 |
| **Depends on** | init, (specflow:generate-qa §5 완료 후) |
| **Notes** | 본문은 Phase 1.5.5 에서 작성. 기존 시나리오 사용자 변경 시 confirm. steps 는 steps_summary 에서 합성 (다단계는 사용자가 수정). |

### validate-scenarios

| 항목 | 내용 |
|---|---|
| **Purpose** | `.e2e/scenarios/*.yml` + config + fixtures 무결성 검증. safety invariant 위반 포함 §A~§F 검사 |
| **Reads** | `.e2e/config.yml`, `.e2e/scenarios/*.yml`, `.e2e/fixtures/`, `.e2e/state.json` (있으면), `openapi/openapi.yaml` (있으면) |
| **Writes** | findings 리포트 (stdout 또는 세션 내) |
| **Storage Tier** | Tier 0 |
| **Depends on** | init, gen-scenarios (또는 수동 작성 시나리오) |
| **Notes** | 본문은 Phase 1.5.6 에서 작성. §A (source write 금지), §B (sandbox name), §C (confirm bypass), §D (시나리오 무결성), §E (auth 정합성), §F (보안 hygiene). |

---

## specflow 섹션 → 스킬 역매핑

| specflow 출력 섹션 | 소비하는 dbflow 스킬 |
|---|---|
| QA §5 E2E DB 시나리오 표 | **gen-scenarios** (시나리오 YAML 자동 생성) |
| QA §5 scenario_name / watch_tables / steps_summary / db_diff_summary | **gen-scenarios** (YAML 필드 매핑) |
| TS §3.2 OpenAPI fragment (path / method / request body) | **gen-scenarios** (steps[].request 합성), **run** (API 서버 path 검증) |
| TS §3.2 OpenAPI fragment → canonical path | **validate-scenarios** §D api_call_match |

---

## 신규 dbflow 스킬 추가 체크리스트

새 스킬을 이 플러그인에 추가할 때는 이 문서의 **스킬별 계약** 섹션에 항목을 먼저 추가한다.

- [ ] Purpose 한 문장
- [ ] Reads: config.yml 어느 섹션, 어떤 파일을 읽는지 구체적으로
- [ ] Writes: 실제 경로 (`.e2e/` 하위)
- [ ] Storage Tier: Tier 0 확인 (dbflow 는 전부 Tier 0)
- [ ] Depends on: 선행 스킬
- [ ] Safety invariant 해당 여부: destructive 명령이면 sandbox 이름 검증 + confirm 필수 명시
- [ ] specflow 역매핑 표 갱신 (해당 시)
