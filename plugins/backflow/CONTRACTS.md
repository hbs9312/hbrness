# backflow — Skill I/O Contracts

> **Scope**: 각 스킬이 어떤 입력(specflow 산출물·레지스트리·선행 스킬 출력)을 읽고 어떤 출력을 어디에 쓰는지 명시한다.
> **Why this doc exists**: `docs/plugin-gaps-and-plan.md` 의 Phase 0 step 2. 새 스킬 추가 시 계약이 암묵적으로 번지면 구현이 "해석"에 의존하게 된다. 이 문서는 계약의 기준선이다.
> **Storage tier**: `plugins/AUTHORING.md` 의 4-tier 규약을 따른다. `src/` 등 프로젝트 소스 트리는 *tier 대상이 아님* (N/A — project code).

## 실행 순서 (canonical)

```
scan-codebase
     │
     ▼
map-tasks                 ← specflow decompose 출력을 파일·레이어에 매핑
     │
     ▼
impl-schema               ← TS §데이터 모델
     │
     ▼
impl-repositories         ← 스키마 + TS §처리 흐름
     │
     ▼
impl-error-codes          ← TS §에러 코드 맵 (+ FS §도메인)   ★Phase 1 (1)
     │                      impl-services 에 앞서 실행 권장
     ▼
impl-services             ← FS §BR/AC + TS §처리 흐름, §오류 처리
     │
     ▼
impl-controllers          ← TS §API 설계
     │
     ▼
impl-middleware           ← TS §보안, §비기능 요구사항 (impl-error-codes 의 HTTP_STATUS_MAP 을 import)
     │
     ▼
impl-integrations         ← TS §인프라, §외부 호출 (B3 stub 교체)
     │
     ▼
generate-tests            ← FS BR/AC + TS 오류 코드
     │
     ▼
validate-{code,api,tests} ← 구현된 코드를 검증
     │
     ▼
patch-backend / reimpl-backend   ← 검증 피드백 반영
```

`impl-*` 각 단계는 모두 `map-tasks` 산출물(`.backflow/task-file-map.md`)을 공통 입력으로 읽는다.

## 핵심 공통 레지스트리

| 파일 | 쓰는 스킬 | 읽는 스킬 | Tier | 비고 |
|---|---|---|---|---|
| `.backflow/service-registry.md` | scan-codebase | map-tasks, impl-repositories, impl-services, impl-controllers, validate-code | Tier 0 | 기존 코드의 서비스·리포지토리·미들웨어·엔티티 레지스트리 |
| `.backflow/task-file-map.md` | map-tasks | 모든 impl-*, validate-code | Tier 0 | 태스크 → 파일·레이어 매핑, commit plan |
| `backend.md` (프로젝트 설정) | — | 모든 스킬 | Tier 0 | 구조·ORM·라우팅·테스트 러너 등 프로젝트 설정. 커밋 대상 |
| `specs/reviews/{TS-docID}-BV2-*.md` | validate-api | (사용자·후속 PR) | Tier 0 | API 검증 리포트 |

## 스킬별 계약

### scan-codebase

| 항목 | 내용 |
|---|---|
| **Purpose** | 기존 서비스·리포지토리·미들웨어·엔티티·유틸을 스캔해 레지스트리 생성 |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | `backend.md` (entity_dir, repository_dir, service_dir, controller_dir, middleware_dir, util_dir) |
| **Writes** | `.backflow/service-registry.md` |
| **Storage Tier** | Tier 0 (프로젝트 작업 디렉토리 워킹 스토리지) |
| **Depends on** | — (가장 먼저) |
| **Notes** | Glob/Grep 기반. 외부 의존성 없음. 기존 프로젝트 플러그인 도입 시점에 1회 실행. |

### map-tasks

| 항목 | 내용 |
|---|---|
| **Purpose** | 구현 태스크를 구체 파일·레이어에 매핑 (선언적 계획) |
| **Reads (specflow)** | `specs/PLAN-*-tasks.md` (decompose 출력), `specs/TS/*` §API 설계, §데이터 모델, §처리 흐름 |
| **Reads (registry/config)** | `.backflow/service-registry.md` (있으면), `backend.md` (structure, module_pattern, naming) |
| **Writes** | `.backflow/task-file-map.md` (task→file, 책임 경계, commit plan by phase) |
| **Storage Tier** | Tier 0 |
| **Depends on** | scan-codebase |
| **Notes** | full/incremental 모드 자동 판단. `backend.md` structure 검증 선행. |

### impl-schema

| 항목 | 내용 |
|---|---|
| **Purpose** | TS 데이터 모델 → DB 스키마 + 마이그레이션 |
| **Reads (specflow)** | `specs/TS/*` §데이터 모델 (엔티티·제약·관계·인덱스) |
| **Reads (registry/config)** | `.backflow/task-file-map.md` (있으면), `backend.md` (database.orm, database.provider), 기존 스키마 파일 (중복 감지) |
| **Writes** | 엔티티·모델·마이그레이션 파일 (ORM 별 경로: Prisma `schema.prisma` / TypeORM `*.entity.ts` / Drizzle `schema.ts` / SQLAlchemy `*.py`), `.backflow/` 진행 로그 |
| **Storage Tier** | N/A — project code (예: `src/entities/`, `migrations/`) |
| **Depends on** | map-tasks |
| **Notes** | ORM-aware. audit 필드(created_at/updated_at/soft delete) 자동. FK 기본 RESTRICT + 경고. 데이터 파괴 변경은 2단계 처리. |

### impl-repositories

| 항목 | 내용 |
|---|---|
| **Purpose** | 데이터 접근 계층(Repository 패턴) 구현 |
| **Reads (specflow)** | `specs/TS/*` §데이터 모델, §처리 흐름 (DB 접근 패턴) |
| **Reads (registry/config)** | `.backflow/service-registry.md`, `.backflow/task-file-map.md`, impl-schema 출력 스키마 파일 |
| **Writes** | Repository 클래스 파일 (패턴별: flat / feature-module / domain-driven) |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-schema |
| **Notes** | 기존 repo 재사용(메서드 append). N+1 방지 강제. 패턴 일관성 확인 필수. |

### impl-error-codes

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §에러 코드 맵 → 백엔드 상수·HTTP 매핑·i18n 리소스 |
| **Reads (specflow)** | `specs/TS/*` §4 에러 코드 맵 (필수), `specs/FS/*` §도메인 정의 (교차검증) |
| **Reads (registry/config)** | `.backflow/task-file-map.md`(있으면), `backend.md` (error_handling.*, framework.language) |
| **Writes** | `src/errors/codes.ts` (enum + ErrorMeta), `src/errors/http-mapping.ts`, `src/locales/errors.{ko,en}.json` (i18n_enabled=true 시) |
| **Storage Tier** | N/A — project code |
| **Depends on** | `map-tasks`. `impl-services` 에 앞서 실행 권장 (서비스가 throw 할 enum 상수 제공) |
| **Notes** | AUTO-GENERATED 주석 필수. Grace period: TS 에 §에러 코드 맵 없으면 기본 5 코드로 임시 동작 + 경고. 언어별 출력(TS/Python/Kotlin) 은 `backend.md.framework.language` 로 분기. 3 시나리오(신규/애드혹 merge/기존 표준) 머지 전략 내장. |

### impl-services

| 항목 | 내용 |
|---|---|
| **Purpose** | 비즈니스 로직 구현 (FS BR + TS 처리 흐름) |
| **Reads (specflow)** | `specs/FS/*` §비즈니스 룰(BR), §수용 기준(AC); `specs/TS/*` §처리 흐름, §오류 처리 |
| **Reads (registry/config)** | `.backflow/service-registry.md`, `.backflow/task-file-map.md`, `backend.md` (error_handling) |
| **Writes** | Service 클래스 파일 (`{service_dir}/{feature}.service.ts`), `src/common/error-codes.ts` 참조 |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-repositories |
| **Notes** | **BR ↔ code 1:1 매핑 강제**. 검증 순서는 TS §처리 흐름 그대로. 외부 호출 패턴(timeout/retry/fallback)은 TS 명시값 사용. |

### impl-controllers

| 항목 | 내용 |
|---|---|
| **Purpose** | API 엔드포인트 핸들러(thin controller) 구현 |
| **Reads (specflow)** | `specs/TS/*` §API 설계 (endpoint·method·request·response·status·error) |
| **Reads (registry/config)** | `.backflow/task-file-map.md`, impl-services 서명, `backend.md` (api.*, request_validation, response_format) |
| **Writes** | Controller 파일 (`{controller_dir}/{feature}.controller.ts`), DTO 파일 (`{dto_dir}/*.dto.ts`), Swagger 데코레이터(doc_tool=Swagger 시) |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-services |
| **Notes** | 컨트롤러에 비즈니스 로직 금지. DTO 검증은 `backend.md.request_validation`(class-validator/zod/joi). 응답 래핑은 `response_format`. |

### impl-middleware

| 항목 | 내용 |
|---|---|
| **Purpose** | 횡단 관심사(auth/authz/error/logging/rate-limit/CORS/validation pipe) |
| **Reads (specflow)** | `specs/TS/*` §보안, §비기능 요구사항; `specs/FS/*` §권한 BR(있으면) |
| **Reads (registry/config)** | `.backflow/task-file-map.md`, impl-controllers 파일 경로, `backend.md` (auth.*, error_handling.*, logging.*, rate_limit.*) |
| **Writes** | Guard·미들웨어 파일 (`{middleware_dir}/{feature}.guard.ts`, `error.filter.ts`, `logger.middleware.ts`, `rate-limit.guard.ts`), error_code→HTTP status 매핑 |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-controllers |
| **Notes** | `auth.strategy`(JWT/Session) · `auth.role_model`(RBAC/ABAC) 기반. error filter 가 AppException → TS error schema 변환. 로깅은 민감 데이터 마스킹. |

### impl-integrations

| 항목 | 내용 |
|---|---|
| **Purpose** | 외부 서비스 통합(MQ·캐시·스토리지·이메일·실시간) |
| **Reads (specflow)** | `specs/TS/*` §인프라, §비동기 처리, §외부 호출 |
| **Reads (registry/config)** | `.backflow/task-file-map.md`, impl-services 의 TODO/stub, `backend.md` (external_services.*) |
| **Writes** | Job processor (`jobs/{feature}.processor.ts`), producer (`jobs/{feature}.producer.ts`), storage/cache/email service 파일, `.env.example` append |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-services, impl-controllers |
| **Notes** | impl-services 가 남긴 stub 을 실제 코드로 교체. 모든 외부 호출에 timeout+retry+fallback 필수. DLQ/상태 업데이트. env 하드코딩 금지. |

### generate-tests

| 항목 | 내용 |
|---|---|
| **Purpose** | 단위·통합 테스트 자동 생성 |
| **Reads (specflow)** | `specs/FS/*` (BR/AC), `specs/TS/*` (error codes, 처리 흐름), `specs/WF/*` (상태 매트릭스) |
| **Reads (registry/config)** | 기존 테스트 파일(패턴 참조), `backend.md` (testing.runner, testing.db_strategy) |
| **Writes** | 테스트 파일 (`{test_dir}/*.spec.ts` 또는 `*.test.ts`, `__tests__/`), 픽스처·모킹 |
| **Storage Tier** | N/A — project code |
| **Depends on** | impl-controllers (또는 임의 레이어) |
| **Notes** | BR → 성공·실패·경계 최소 3 테스트. 에러 코드마다 status + body 검증. 외부 의존성 mock. AAA 패턴. |

### validate-code

| 항목 | 내용 |
|---|---|
| **Purpose** | 구현 코드를 컨벤션·레이어 경계·에러 처리·타입 안정성·보안 관점에서 점검 |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | `.backflow/task-file-map.md`, `backend.md` |
| **Writes** | findings YAML(path·line·severity·suggestion), 요약 리포트 (파일 쓰기는 없음 — stdout 또는 세션 내) |
| **Storage Tier** | N/A |
| **Depends on** | impl-schema ~ impl-integrations |
| **Notes** | `disable-model-invocation: true`. 필수 체크: 네이밍/구조, 레이어 격리(순환 금지), 에러 처리 커버리지, `any` 금지, SQL 인젝션·secrets·입력 검증. |

### validate-api

| 항목 | 내용 |
|---|---|
| **Purpose** | 구현 API 가 TS 계약과 일치하는지 클린룸 검증 |
| **Reads (specflow)** | `specs/TS/*` §API 설계 |
| **Reads (registry/config)** | `backend.md` |
| **Writes** | `specs/reviews/{TS-docID}-BV2-{YYYYMMDD-HHmmss}.md` |
| **Storage Tier** | Tier 0 (`specs/reviews/`) |
| **Depends on** | impl-controllers |
| **Notes** | 서브에이전트 `backflow:validator-api` 에 위임. 격리 컨텍스트. |

### validate-tests

| 항목 | 내용 |
|---|---|
| **Purpose** | 테스트 커버리지 검증 (BR / 에러코드 / 경계값 / 격리 / 모킹 / 어서션 품질) |
| **Reads (specflow)** | `specs/FS/*` (BR), `specs/TS/*` (error codes), `specs/WF/*` (상태 매트릭스) |
| **Reads (registry/config)** | 테스트 파일, 대상 소스 파일 |
| **Writes** | 커버리지 findings (missing BR·에러코드·경계값), 품질 이슈 |
| **Storage Tier** | N/A |
| **Depends on** | generate-tests |
| **Notes** | `disable-model-invocation: true`. |

### patch-backend

| 항목 | 내용 |
|---|---|
| **Purpose** | validate-* 피드백을 최소 수정으로 반영 |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | validate-* findings YAML |
| **Writes** | 대상 소스 파일(Edit only, 재작성 금지), change log YAML |
| **Storage Tier** | N/A — project code 수정 |
| **Depends on** | validate-code / validate-api / validate-tests |
| **Notes** | 단일 파일 변경 선호. 시그니처 변경 시 mock 동기화. 부수효과 기록. |

### reimpl-backend

| 항목 | 내용 |
|---|---|
| **Purpose** | 구조적 문제(레이어 위반·순환·트랜잭션 범위·데이터 모델 변경) 재구현 |
| **Reads (specflow)** | — |
| **Reads (registry/config)** | validate-* findings, 프로젝트 구조, 의존 파일 Grep |
| **Writes** | 대상 파일 전체 재구현 + 테스트 업데이트 + change log |
| **Storage Tier** | N/A — project code 재작성 |
| **Depends on** | patch-backend + regression 감지 |
| **Notes** | 가능한 한 interface 유지. 재구현 후 해당 validate-* 재실행. |

## specflow 섹션 → 스킬 역매핑

한 섹션이 누락되면 어떤 스킬이 깨지는지 빠르게 파악하기 위한 역인덱스.

| specflow 출력 섹션 | 소비하는 backflow 스킬 |
|---|---|
| FS §비즈니스 룰(BR) | impl-services, generate-tests, validate-tests |
| FS §수용 기준(AC) | impl-services, generate-tests |
| FS §권한 BR | impl-middleware |
| TS §데이터 모델 | impl-schema, impl-repositories |
| TS §API 설계 | impl-controllers, validate-api |
| TS §처리 흐름 | impl-repositories, impl-services |
| TS §에러 코드 맵 | **impl-error-codes**, impl-middleware (HTTP 매핑 import), generate-tests, validate-tests |
| TS §오류 처리 (sequence 내 에러 흐름) | impl-services, generate-tests, validate-tests |
| TS §보안 | impl-middleware |
| TS §비기능 요구사항 | impl-middleware |
| TS §인프라·외부 호출 | impl-integrations |
| WF §상태 매트릭스 | generate-tests, validate-tests |
| PLAN-*-tasks.md (decompose) | map-tasks |

> **Phase 1 로드맵 영향**: `docs/plugin-gaps-and-plan.md` §3.7 에서 TS 에 "관측성 요건", "OpenAPI fragment" 섹션이 추가 의무화될 예정 — 그 시점에 `impl-observability`, `export-api-contract` 행이 추가된다. 에러 코드 맵 관련 행은 이미 반영 완료(Phase 1 (1) 완료). `impl-middleware` 는 다음 커밋에서 `impl-error-codes` 의 `HTTP_STATUS_MAP` 을 import 하도록 문서 정리 필요.

## 신규 backflow 스킬 추가 체크리스트

새 스킬을 이 플러그인에 추가할 때는 이 문서의 **스킬별 계약** 섹션에 항목을 먼저 추가한다. PR 에서 계약표가 갱신되지 않았다면 리뷰어가 바로 반려한다.

- [ ] Purpose 한 문장
- [ ] Reads (specflow): 섹션 이름까지 구체적으로
- [ ] Reads (registry/config): `backend.md` 어느 키를 보는지 명시
- [ ] Writes: 실제 경로·파일 네이밍 패턴 (예시 경로 포함)
- [ ] Storage Tier: AUTHORING.md 규약과 일치
- [ ] Depends on: 선행 스킬
- [ ] specflow 섹션 → 스킬 역매핑 표 갱신
