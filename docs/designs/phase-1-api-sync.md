# Phase 1 (3) — API 계약 동기화 Skill 설계

> **Generated**: 2026-04-26
> **Scope**: Phase 1 세 번째 항목 — `backflow:export-api-contract` 신설 + `frontflow:sync-api-client` 신설 + 기존 `frontflow:impl-api-integration` 책임 분리 + `specflow:generate-ts §3 API 설계` 에 OpenAPI fragment 부속섹션 의무화 + 양 플러그인 `validate-code` §9 drift 룰
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.3 (3), §3.7
> **Companion designs**: `docs/designs/phase-1-error-contract.md` (Phase 1 (1)), `docs/designs/phase-1-observability.md` (Phase 1 (2)) — 본 문서와 패턴 동일
>
> **Revision (2026-04-26, Task 0 codex review — 8 findings, 2 critical · 5 warning · 1 info)**:
> - **XR-001 (critical)**: `components.responses` 자동 합성 책임을 `specflow:generate-ts` → **`backflow:export-api-contract`** 로 이전. specflow 는 TS 내부 §3.2 ↔ §4 일관성 룰만 검증.
> - **XR-002 (critical)**: Phase 1 라우트 introspection 지원 범위 축소 — TypeScript/Node (NestJS·Express·Fastify) **first-class**, 나머지(Python·Java·Go·Rust)는 path/method/auth 만 + schema=manual TODO. Scenario B `routes-only` 는 신뢰도 등급 출력 의무화.
> - **XR-003 (warning)**: OpenAPI 에 `components.schemas.ErrorCode` enum 도입 → `ErrorEnvelope.error.code` 가 enum 을 $ref. Phase 1 (1) "코드 문자열이 계약의 바이트" 의 type-safety 보강.
> - **XR-004 (warning)**: `validate-code` §9 drift 룰을 §7·§8 패턴의 구체 YAML 블록으로 본 문서에 추가 (§4.4 확장).
> - **XR-005 (warning)**: path canonicalization 규칙 명시 — §3.1 표 경로는 `servers[].url` 제외한 path 만 (fragment 와 동일).
> - **XR-006 (warning)**: Phase 1 generator 단일화 — `openapi-typescript-codegen` 만 first-class, `orval`·`openapi-zod-client` 는 experimental, `manual` 은 types+fetch 만.
> - **XR-007 (warning)**: drift 검출 메커니즘 강화 — `info.version` (계약 표면 변경 시만) + 별도 `contractHash` 이중 박제. `.frontflow/api-contract.lock` 신설.
> - **XR-008 (info)**: 기각 대안 보강 — OpenAPI 3.0 vs 3.1, annotation-first, AsyncAPI.

## 목표

Backend 라우트와 Frontend API 클라이언트가 **하나의 OpenAPI 문서를 source of truth** 로 공유하도록 자동화한다. 백엔드는 TS §3 + 실제 라우트로부터 `openapi/openapi.yaml` 을 export 하고, 프론트엔드는 그 문서로부터 클라이언트·타입·MSW 핸들러를 codegen 한다. `frontflow:impl-api-integration` 은 더 이상 클라이언트·타입을 hand-write 하지 않고 **codegen 결과를 import + 비즈니스 와이어링** 만 담당한다.

### Non-goals (이 skill 의 책임이 아님)

- 라우트·컨트롤러 구현 — `backflow:impl-controllers` 책임 (현재 동작 유지)
- API 설계 결정·ADR — `specflow:generate-ts` 책임 (TS §1 ADR + §3 API 설계)
- 백엔드 응답 envelope (`{success, data, error}`) — `backflow:impl-middleware` 책임. OpenAPI components 의 `Error` 스키마는 본 skill 이 §4 에러 코드 맵을 읽어 자동 생성하지만 envelope 자체는 변경하지 않음
- 프론트엔드 UI 분기·렌더 — `frontflow:impl-error-handling` (Phase 1 (1)) + `frontflow:impl-api-integration` (Phase 1 (3) 후 housekeeping) 책임
- gRPC / GraphQL / tRPC schema — Phase 2 어댑터 후보. 본 Phase 는 **OpenAPI 3.1 (REST)** 만
- 백엔드 stub server (mock backend) — frontend MSW 핸들러로 충분. `prism` 같은 별도 mock 서버는 Phase 2
- API 버저닝(v1/v2 병존), Deprecation 헤더 — Phase 2 (`backflow:impl-api-versioning`)
- Contract test (Pact 등) — Phase 2

## 1. TS 포맷 변경 — `§3 API 설계` 하위에 OpenAPI fragment 의무화

`specflow:generate-ts` 출력의 §3 API 설계 (현재 freeform 표 형식) 하위에 **OpenAPI 3.1 fragment** 부속섹션을 추가한다. 기존 freeform 표(METHOD/경로/Request/Response/Error Responses)는 인간 가독용으로 유지하되, OpenAPI fragment 를 **기계 파싱 source of truth** 로 둔다. **단, fragment 의 `components.responses` 합성은 specflow 가 아니라 `backflow:export-api-contract` 가 export 시점에 §4 에러 코드 맵에서 수행** (XR-001).

### 섹션 포맷

```markdown
## 3. API 설계

### 3.1 엔드포인트 표 (인간 가독)

> 경로는 `servers[].url` 또는 `backend.md.api.base_path` 를 **제외**한 canonical path 로 통일. 비교·매칭은 항상 canonical path 기준 (XR-005).

| METHOD | 경로 (canonical) | 요약 | 인증 | 기능 참조 |
|---|---|---|---|---|
| POST | /speakers/enroll | 화자 등록 | required | AC-001, BR-003 |
| GET | /speakers | 화자 목록 | required | AC-002 |

### 3.2 OpenAPI Fragment (source of truth)

```yaml
openapi: 3.1.0
info:
  title: {project name}
  version: {semver}     # 계약 표면 변경 시만 bump (라우트 내부 구현 변경은 미해당)
servers:
  - url: /api/v1
    description: production
paths:
  /speakers/enroll:        # canonical path — base_path 제외
    post:
      operationId: enrollSpeaker
      summary: 화자 등록
      tags: [speakers]
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              $ref: '#/components/schemas/EnrollRequest'
      responses:
        '201':
          description: created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/EnrollResponse'
        # ↓ status → ErrorCode 매핑만 specflow 단계에서 작성. components.responses 본문은 export 시 합성됨.
        '400':
          $ref: '#/components/responses/AUDIO_TOO_SHORT'
        '409':
          $ref: '#/components/responses/SPEAKER_DUPLICATE_NAME'
components:
  schemas:
    EnrollRequest:
      type: object
      required: [name, audio_file, workspace_id]
      properties:
        name: { type: string, minLength: 1, maxLength: 64 }
        audio_file: { type: string, format: binary }
        workspace_id: { type: string, format: uuid }
    EnrollResponse:
      type: object
      required: [speaker_id, name, embedding_status, created_at]
      properties:
        speaker_id: { type: string, format: uuid }
        name: { type: string }
        embedding_status: { $ref: '#/components/schemas/EmbeddingStatus' }
        created_at: { type: string, format: date-time }
    EmbeddingStatus:
      type: string
      enum: [pending, processing, ready, failed]
    # AUTO-INJECTED by export-api-contract from §4 에러 코드 맵 — 이 fragment 에선 placeholder
    ErrorCode:
      type: string
      description: '§4 에러 코드 맵에서 export 시 enum 으로 합성됨'
    ErrorEnvelope:
      type: object
      required: [error]
      properties:
        error:
          type: object
          required: [code, message]
          properties:
            code: { $ref: '#/components/schemas/ErrorCode' }   # XR-003: enum $ref
            message: { type: string }
            meta: { type: object, additionalProperties: true }
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  # responses 섹션은 specflow 단계에서 비워둔다. export-api-contract 가 §4 행마다 합성.
  responses: {}
```
```

### 섹션 규약

| 필드 | 필수 | 규칙 / 비고 |
|---|---|---|
| §3.1 엔드포인트 표 | required | 인간 가독용 — 기능 참조(AC/BR) 매핑 유지. **canonical path** (servers.url 제외) 로 통일 |
| §3.2 OpenAPI fragment | required (grace 기간 warning) | 기계 파싱 대상. fenced code block 언어 태그 `yaml` |
| `info.version` | required | semver. **계약 표면 변경 시만** bump (path/method 추가·제거, schema 필드 추가·제거·타입 변경, security 변경). 라우트 내부 구현 변경은 미해당 (XR-007) |
| `paths.*` | canonical path | `servers.url` 제외. base path strip 후 비교 |
| `paths.*.operationId` | required | camelCase. 코드젠 함수명·query key 의 안정 ID. §3.1 표와 1:1 |
| `components.schemas.ErrorCode` | placeholder | specflow 는 placeholder 만, **export 가 §4 의 모든 code 로 enum 채움** |
| `components.schemas.ErrorEnvelope.error.code` | $ref ErrorCode | string 직접 사용 금지 (XR-003) |
| `components.responses` | empty `{}` | specflow 단계에서 비움. **export 가 §4 행마다 합성** (XR-001) |
| `components.securitySchemes` | required (인증 있을 시) | TS §보안 섹션과 일치 |

**용어 통일**: `operationId` (camelCase) — TS·OpenAPI fragment·codegen 함수명·queryKey 첫 인자 모두 같은 값.

### `specflow:generate-ts` 변경

- 프롬프트에 "§3 API 설계 하위에 §3.2 OpenAPI fragment 부속섹션 반드시 포함" 추가
- 자가 점검 체크리스트:
  - "OpenAPI fragment 가 §3.1 표의 모든 엔드포인트를 커버 (operationId 1:1)"
  - "§3.1 표의 경로가 canonical path (servers.url 제외) 로 통일"
  - "§3.2 의 `paths.*.responses` 가 §4 의 ErrorCode 만 status 와 함께 매핑하고, `components.responses` 본문은 작성하지 않음 (export 책임)"
  - "ErrorEnvelope.error.code 가 ErrorCode 를 `$ref`"
- 기존 §3 freeform 만 있는 TS 재생성 시: 표를 파싱해서 OpenAPI fragment 초안을 자동 합성 (사람이 검토 후 확정)
- **비**(non-)책임 — `components.responses` 본문, `ErrorCode` enum 의 실제 값. 둘 다 export-api-contract 가 합성

### `specflow:validate/rules/ts-rules.md` 신규 룰 (warning — v1.x grace; v2.0 critical 승격)

```markdown
## API 계약 (warning — v1.x grace period; v2.0 critical 승격 예정)
40. §3.2 OpenAPI fragment 부속섹션 존재 — 누락 시 warning + skill 은 §3.1 표 파싱 폴백
41. fragment 의 openapi 필드가 `3.1.x` — 그 외 warning (3.0.x 는 `nullable` 등 차이로 자동 보정 권고)
42. §3.1 표의 모든 (METHOD, canonical path) 가 fragment.paths 에 존재 — 비교는 base_path strip 후. 누락 시 warning
43. fragment 의 모든 path 에 operationId 존재 (camelCase, 전역 유일) — 위반 시 warning
44. §4 에러 코드 맵 의 모든 code 가 fragment 의 어느 path 의 `responses[status].$ref: '#/components/responses/{CODE}'` 로 등장 — 누락 시 warning ("API 에서 안 쓰이는 에러 코드면 의도 확인")
45. fragment.paths.*.responses 의 모든 `$ref` target 이 §4 에 존재 — 미존재 시 warning ("orphan response ref")
46. fragment.components.schemas.ErrorEnvelope.error.code 가 `$ref: '#/components/schemas/ErrorCode'` — 그 외(특히 `type: string`) 시 warning (XR-003)
47. fragment 내부 `$ref` 가 모두 같은 fragment 안에서 해소 가능 — broken ref → critical (TS 내부 무결성)
48. fragment.components.securitySchemes 가 §보안 섹션의 인증 방식과 일치 — 위반 시 warning
49. fragment.components.responses 가 비어 있음 (`{}`) — 비어 있지 **않으면** warning ("specflow 단계에서 합성 책임 침범 — export-api-contract 책임")
```

룰 47 만 critical 인 이유: broken `$ref` 는 fragment 자체가 invalid OpenAPI 문서가 되어 export skill 이 fail 함. 다른 룰들은 grace 동안 export 가 폴백 동작 가능.

## 2. `backflow:export-api-contract` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §3.2 OpenAPI fragment + §4 에러 코드 맵 + 실제 컨트롤러 라우트 → 단일 `openapi/openapi.yaml` 문서로 export. **`components.schemas.ErrorCode` enum 채움 + `components.responses` 합성** + TS ↔ 라우트 drift 1차 검출 |
| **Reads (specflow)** | `specs/TS/*` §3 API 설계 (특히 §3.2 OpenAPI fragment), `specs/TS/*` §4 에러 코드 맵 (**필수 — components 합성 입력**) |
| **Reads (registry/config)** | `.backflow/task-file-map.md`(있으면), `backend.md` (`api_contract.*` 섹션 신설, `api.*`, `framework.*`, `error_handling.error_code_enum`), 컨트롤러 파일 (라우트 데코레이터·decorator) |
| **Writes** | `openapi/openapi.yaml` (또는 `.json` — `backend.md.api_contract.format`), `.backflow/api-contract-drift.md` (export 시점 TS ↔ route 차이 리포트) |
| **Storage Tier** | N/A — project artifact. `openapi/` 디렉토리는 프로젝트 루트, commit 대상 |
| **Depends on** | `map-tasks`, `impl-error-codes` (§4 합성 입력), `impl-controllers` (라우트가 존재해야 export 가능 — `source: ts-and-routes` 모드 시). `impl-services` 와 무관 (서비스 시그니처가 아니라 라우트 표면만 본다) |
| **Notes** | OpenAPI 3.1 only. Vendor lock-in 0건. AUTO-GENERATED 멱등성. **`components.schemas.ErrorCode` enum 과 `components.responses` 본문 합성은 이 skill 의 단독 책임** (specflow 는 placeholder 만 둠). `backend.md.api_contract.source` 가 `ts-only` 이면 fragment 만 사용 (라우트 미검증 — 신규 프로젝트 grace) |

### 합성 책임 (XR-001)

specflow 는 fragment **틀**만 작성한다. export-api-contract 는 export 시점에:

1. `components.schemas.ErrorCode` 의 `enum` 배열을 §4 의 모든 code 로 채움
2. `components.responses` 를 §4 의 모든 code 행에 대해 합성:
   ```yaml
   {ERROR_CODE}:
     description: '{message_ko} (또는 message_en)'
     content:
       application/json:
         schema: { $ref: '#/components/schemas/ErrorEnvelope' }
         example:
           error:
             code: {ERROR_CODE}
             message: {message_ko 또는 message_en}
   ```
3. fragment.paths.*.responses 의 `$ref` 와 합성 결과의 키가 1:1 매칭하는지 확인 (불일치 시 drift 리포트)

이 책임 분리로:
- TS 작성자는 §4 행 추가만으로 자동으로 OpenAPI components.responses 가 따라옴
- specflow 는 §3.2 ↔ §4 의 매핑만 검증 (ts-rules 44, 45, 49)
- export skill 은 합성 + drift 만 담당

### 입력 우선순위 (3-way reconciliation)

```
Source 1: TS §3.2 OpenAPI fragment        (specflow source of truth — 의도)
Source 2: TS §4 에러 코드 맵                (specflow — components 합성 입력)
Source 3: 컨트롤러 라우트 코드             (backflow 실제 구현 — 사실)
Source 4: backend.md.api_contract.* 설정  (출력 형식 옵션)

→ Reconcile:
  - paths 집합:
      A. fragment 에만 있음 → critical drift (TS 명시했으나 미구현)
      B. 라우트에만 있음    → critical drift (의도 없는 endpoint — TS 누락 또는 비밀 endpoint)
      C. 양쪽 존재         → fragment.method/path 우선, 라우트는 검증 보조
  - Schema (request/response):
      D. fragment schema 가 라우트 DTO 와 호환 안 됨 → warning (자동 화해 어려움; drift 리포트에 "수동 확인" 표시)
  - Auth:
      E. fragment.security != 라우트의 guard decorator → warning
  - components 합성:
      F. §4 에 있는데 fragment.paths 어디에서도 참조 안 됨 → info ("API 에서 미사용 — 도메인 throw 만 하는 코드일 수 있음")
      G. fragment 가 참조하는데 §4 에 없음 → critical drift (TS 자체 무결성)
  → 최종 export: fragment 를 기준으로 작성하고 components.responses 는 §4 에서 합성. drift 는 `.backflow/api-contract-drift.md` 로 별도 리포트
```

이 reconciliation 은 **export 시점 1회**. 지속 검증은 `validate-code` §9 가 담당.

### 실행 위치 (canonical 흐름)

```
map-tasks
   │
   ▼
impl-schema → impl-repositories → impl-error-codes
                                       │
                                       ▼
                               impl-observability
                                       │
                                       ▼
                               impl-services
                                       │
                                       ▼
                               impl-controllers   ★ 라우트 표면 완성
                                       │
                                       ▼
                               impl-middleware
                                       │
                                       ▼
                               impl-integrations
                                       │
                                       ▼
                               export-api-contract  ★ §3.2 + §4 + 라우트 → openapi.yaml
                                       │
                                       ▼  (consumed by frontflow:sync-api-client)
                               generate-tests
```

### `backend.md` 신규 키

```yaml
api_contract:
  source: "ts-and-routes"     # ts-only | ts-and-routes (default) | routes-only
                              # ts-only: 신규 프로젝트, 라우트 아직 없음 — fragment 만 export
                              # routes-only: 레거시 프로젝트, TS §3.2 없음 — fragment 자동 합성 + 신뢰도 등급 출력 (warning)
  output_path: "openapi/openapi.yaml"   # commit 대상. format=json 시 .json 으로 변경
  format: "yaml"              # yaml (default) | json
  servers:                    # OpenAPI servers 배열 (없으면 framework convention default)
    - url: "/api/v1"
      description: "production"
  emit_examples: true         # responses.examples 자동 생성 여부 (TS 의 example 또는 schema 의 default 사용)
  drift_report_path: ".backflow/api-contract-drift.md"
  exclude_paths:              # internal endpoint (admin, health 등) export 제외
    - "/internal/**"
    - "/health"
  # XR-007: contractHash 박제 — info.version 외 별도 fingerprint
  contract_hash_alg: "sha256" # paths/schemas/security 의 정렬된 직렬화 hash
```

### 언어·프레임워크 지원 매트릭스 (Phase 1, XR-002)

| framework / language | Phase 1 지원 등급 | 라우트 추출 | request/response schema 추출 |
|---|---|---|---|
| **NestJS (TypeScript)** | **first-class** | `@Controller` + `@Get/@Post/...` decorator | DTO 클래스 + class-validator → JSON schema (어댑터 내장) |
| **Express (TypeScript)** | **first-class** | `router.{method}(path, ...)` 호출 패턴 + 라우터 mount 합성 | request/response 본문 schema 는 zod / type assertion 검출. 미검출 시 manual TODO |
| **Fastify (TypeScript)** | **first-class** | `fastify.route` / shorthand | `schema` 옵션 (Fastify 내장 JSON Schema) — 직접 흡수 |
| FastAPI (Python) | path/method/auth | decorator + Pydantic 모델 path | schema 추출 = **manual TODO 마커**. drift 리포트에 "manual" 표시 |
| Spring Boot (Java/Kotlin) | path/method/auth | `@RequestMapping` family | schema = **manual TODO** |
| Go (chi/gin) | `ts-only` 권장 | 자동 추출 어려움 | `source: ts-only` 강제 권고 (warning) |
| Rust (axum/actix) | `ts-only` 강제 | 자동 추출 미지원 | `source: ts-only` 만 허용 |
| 기타 | `ts-only` 만 | — | — |

**중요**: skill 은 first-class 가 아닌 언어에서 `source: ts-and-routes` 시도 시 **warning + 부분 추출** 동작. fragment 가 source of truth — 라우트가 더 풍부해도 fragment 에 없으면 export 안 됨 (drift 리포트 → critical).

`routes-only` 모드 출력에는 신뢰도 등급 표시:
- `confidence: high` — first-class 프레임워크에서 schema 까지 자동 추출됨
- `confidence: medium` — path/method/auth 만 추출. schema 는 manual TODO
- `confidence: low` — heuristic 기반 부분 추출. 사람 review 필수

## 3. `frontflow:sync-api-client` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | `openapi/openapi.yaml` → TS API 클라이언트 함수 + 타입 정의 + (옵션) MSW 핸들러 codegen. `info.version` + `contractHash` 이중 박제로 stale 검출 |
| **Reads (specflow)** | — (직접 읽지 않음. OpenAPI 가 specflow 의 indirect 출력) |
| **Reads (registry/config)** | `.frontflow/task-file-map.md`(있으면), `frontend.md` (`api_contract.*` 섹션 신설, `api_client.method`, `server_state`), OpenAPI 문서 (path or URL), `.frontflow/api-contract.lock` (이전 sync 의 version/hash) |
| **Writes** | `src/api/generated/{tag}.ts`, `src/api/types.gen.ts` (전체 schema 타입), (옵션) `src/mocks/handlers.gen.ts`, **`.frontflow/api-contract.lock`** (version/hash/source etag 박제) |
| **Storage Tier** | N/A — project code. `generated/` / `*.gen.ts` 는 commit 대상이지만 사람 편집 금지. `.frontflow/api-contract.lock` 도 commit 대상 |
| **Depends on** | `map-tasks`. **`backflow:export-api-contract` 가 먼저 실행되어 `openapi/openapi.yaml` 이 존재해야 함**. `impl-error-handling` 와 무관 — 에러 코드는 OpenAPI components.schemas.ErrorCode enum 으로 흡수 |
| **Notes** | Phase 1 default generator = **`openapi-typescript-codegen`** 단일 first-class. 다른 generator 는 experimental. AUTO-GENERATED 주석 + 헤더에 `info.version` + `contractHash` 박제. version+hash mismatch 시 validate critical |

### 출력 구조

```
src/api/generated/
  ├── speakers.ts          # tag=speakers 의 모든 operationId
  ├── workspaces.ts
  └── index.ts
src/api/
  ├── types.gen.ts         # components.schemas → TypeScript types (ErrorCode enum 포함)
  └── client.ts            # 사람 작성 — fetch/axios/ky 인스턴스 (impl-api-integration 책임)
src/mocks/
  ├── handlers.gen.ts      # MSW handlers (emit_msw=true 시)
  └── server.ts            # 사람 작성
.frontflow/
  └── api-contract.lock    # { version, contract_hash, source_etag, generated_at, generator } JSON
```

### `frontend.md` 신규 키

```yaml
api_contract:
  source: "openapi/openapi.yaml"   # 모노레포 상대경로 또는 URL (예: https://api.example.com/openapi.json)
                                   # URL 인 경우 sync-api-client 가 fetch + cache (~/.hbrness/api-contract/{hash}.yaml)
  source_etag_file: ".frontflow/api-contract.etag"   # URL 모드 stale 검출용
  contract_lock_file: ".frontflow/api-contract.lock" # XR-007: version/hash/etag 박제 lock
  generator: "openapi-typescript-codegen"  # Phase 1 first-class 단일. 그 외(orval/openapi-zod-client)는 experimental, manual=types+fetch only
  client_dir: "src/api/generated"
  types_file: "src/api/types.gen.ts"
  msw_handlers_file: "src/mocks/handlers.gen.ts"
  emit_msw: true               # MSW 핸들러 자동 생성 (false 시 types + client 만)
  emit_query_keys: true        # tanstack-query 사용 시 queryKey 상수 자동 생성 (Phase 1: openapi-typescript-codegen 만 지원)
  pinned_version: ""           # info.version 핀 (생성 시 박제). validate 가 mismatch 검출
  runtime_assertion: false     # XR-007: 런타임 version assertion (opt-in, Phase 2)
```

### Generator 옵션 (XR-006)

| generator | Phase 1 등급 | 출력 범위 | 비고 |
|---|---|---|---|
| **`openapi-typescript-codegen`** | **first-class (default)** | types + 함수 + axios/fetch + queryKey | 단일 안정 지원 |
| `orval` | experimental | types + 함수 + tanstack-query 훅 + MSW | 옵션 많음 — Phase 2 stable 지원 |
| `openapi-zod-client` | experimental | types + 함수 + zod 런타임 검증 | 빌드 사이즈 ↑, runtime 검증 — Phase 2 |
| `manual` | minimal | **types + fetch 함수만** (MSW/queryKey 미지원) | external 의존 회피용. 출력 범위 명시적 제한 |

`emit_msw: true` 와 `emit_query_keys: true` 는 generator 가 지원하는 경우만 동작. 미지원 generator + true 조합은 sync-api-client 가 warning 출력 + 옵션 무시.

## 4. 동기화 메커니즘 — TS as source of truth, OpenAPI as transport

```
specs/TS/*.md
  §3.2 OpenAPI fragment ──────► (source of truth)
  §4 에러 코드 맵      ──────► (components 합성 입력)
                                       │
                                       ▼
backend codebase                       │
  controllers/*.ts ─────► export-api-contract
                              ▲          │
                              │          ▼  (artifact)
                              │     openapi/openapi.yaml ──┐
                              │     (info.version +        │
                              │      contractHash 박제)     ▼
                              │                      sync-api-client
                              │                      ┌─ check ─┐
                              │                      │  lock vs│
                              │                      │  current │
                              │                      └─────────┘
                              │                            │
                              │                            ▼
                              │                  src/api/generated/*
                              │                  src/api/types.gen.ts
                              │                  src/mocks/handlers.gen.ts
                              │                  .frontflow/api-contract.lock
                              │                            │
                              │                            ▼
                              │                  impl-api-integration
                              │                  (import + wire)
                              │                            │
                              │   ┌────────────────────────┘
                              │   │
                              ▼   ▼
                     validate-code §9
                     (양방향 hash drift)
```

### 채택 방식 — "TS fragment first, route validates, hash binds"

- **계약의 바이트**: `openapi.yaml` 의 `info.version` (계약 표면 변경 시만 bump) + `contractHash` (paths + schemas + security 의 정렬 직렬화 sha256). 둘 다 frontend codegen 시 헤더에 박제 + `.frontflow/api-contract.lock` 에 기록. `validate-code` 가 mismatch 시 critical.
- **양 방향**:
  - TS §3.2 변경 → `export-api-contract` 재실행 → `openapi.yaml` 갱신 → `info.version` 또는 `contractHash` 변동 → frontend `sync-api-client` 재실행 필요 → validate 가 stale 경고
  - 라우트만 변경 (TS 갱신 없이 컨트롤러 시그니처 변경) → `export-api-contract` 가 drift 리포트 + critical → 사용자가 TS 또는 코드 정정
  - 라우트 **내부 구현만** 변경 (서비스 호출 로직 변경, 라우트 표면 동일) → `info.version` 변동 없음, `contractHash` 도 동일 → frontend 재생성 불필요

### 기각한 대안 (XR-008 보강)

| 대안 | 기각 이유 |
|---|---|
| **(a) 코드 first (route → TS 자동 생성)** | 의도(TS) 가 구현(코드) 에 종속됨. 명세가 코드 변경에 끌려다니게 되어 specflow 의 톱다운 원칙 위배. freeform 라우트 코멘트 노이즈가 TS §3 에 유입 |
| **(b) tRPC schema 도입** | TypeScript-only — 다언어 백엔드(Java/Python/Go) 미지원. Phase 2 어댑터 후보로 보류 |
| **(c) protobuf / gRPC** | 본 phase 목적(REST API 동기화) 과 다름. gRPC 도입 프로젝트는 별도 skill (Phase 2) |
| **(d) GraphQL schema** | 동등하게 강력하지만 REST 와 양립 불가. 이번 Phase 는 REST 만 |
| **(e) JSON Schema 단독 (OpenAPI 없이)** | path/method/operationId/security 정보 부재 — 라우트 매칭 불가 |
| **(f) Backend export type → Frontend import (모노레포 한정)** | Phase 1 (1) 와 같은 이유로 기각. polyrepo 미지원 + 런타임 의존성 lockstep 비용 |
| **(g) OpenAPI 3.0** | 3.1 vs 3.0 차이: 3.1 은 JSON Schema 2020-12 정합 + `nullable` 제거 + `examples` 배열 표준화. 3.0 도구 호환을 원할 시 export skill 의 `format` 옵션으로 다운컨버트 (Phase 2) |
| **(h) annotation-first (nestjs/swagger / drf-spectacular)** | 코드 first 의 변형 — 명세가 코드 decorator 에 종속. (a) 와 동일 사유로 기각. 단 export-api-contract 가 일부 메타데이터 보강용으로 *읽기만* 하는 것은 허용 |
| **(i) AsyncAPI** | SSE / WebSocket / 메시지 큐용. REST 와 별개 트랙. 본 phase 에서 SSE 명시 endpoint 는 OpenAPI `text/event-stream` content-type 으로 처리. 풀 AsyncAPI 도입은 Phase 2 |

### Drift 방지 — 핵심 invariant (XR-007 강화)

1. `openapi.yaml.info.version` 은 **계약 표면 변경 시에만** bump (path/method 추가·제거, schema 필드 추가·제거·타입 변경, security 변경). 라우트 내부 구현 변경은 미해당.
2. `openapi.yaml.contractHash` (sha256) 는 paths + schemas + securitySchemes 를 정렬 직렬화 후 hash. 어떤 표면 변경에도 변동.
3. Frontend `sync-api-client` 는 두 값을 **헤더 주석 + `.frontflow/api-contract.lock`** 양쪽에 박제.
4. `openapi/openapi.yaml`, `.backflow/api-contract-drift.md`, `src/api/generated/**`, `src/api/types.gen.ts`, `.frontflow/api-contract.lock` 모두 **commit 대상**. CI 에서 `--check` 모드로 dirty diff 검출.
5. 런타임 assertion (frontend 가 client.ts 에서 응답의 `x-api-version` 헤더와 박제값 비교) 은 **opt-in** (`runtime_assertion: true`). Phase 1 default false.

### Validate-code §9 drift 룰 (XR-004 — 양 플러그인 공통 사양)

#### Backflow §9 (`backflow:validate-code` 추가) — critical

```yaml
입력:
  ts_section: specs/TS-*.md §3.2 OpenAPI fragment + §4 에러 코드 맵
  openapi_file: backend.md.api_contract.output_path (예: openapi/openapi.yaml)
  drift_report: backend.md.api_contract.drift_report_path (.backflow/api-contract-drift.md)
  controllers_dir: backend.md.structure.controller_dir
  api_contract_source: backend.md.api_contract.source

검사 항목 — TS ↔ openapi.yaml 일관성:
  fragment_paths_subset:
    - TS §3.2 fragment.paths 의 (METHOD, canonical path) 가 openapi.yaml.paths 에 존재하지 않으면 → critical
    - openapi.yaml.paths 에 있으나 TS §3.2 에 없으면 → critical (export 가 라우트만 보고 추가했으나 TS 갱신 안 됨)
  components_responses_synthesized:
    - openapi.yaml.components.responses 의 키 집합 == §4 의 모든 code 집합 → 불일치 시 critical
    - components.responses.{CODE}.example.error.code != {CODE} → critical
  errorcode_enum_filled:
    - openapi.yaml.components.schemas.ErrorCode.enum 이 §4 의 모든 code 와 1:1 → 불일치 시 critical
    - openapi.yaml 에 ErrorCode 가 placeholder (description 만) 남아 있으면 → critical (export 미실행 또는 실패)
  ts_fragment_responses_empty:
    - TS §3.2 fragment.components.responses != {} → warning ("specflow 책임 침범")

검사 항목 — openapi.yaml ↔ 라우트 일관성 (api_contract.source: ts-and-routes 시):
  paths_match:
    - 라우트 추출 결과 ⊄ openapi.yaml.paths → critical (orphan route)
    - openapi.yaml.paths ⊄ 라우트 → critical (missing route)
    - 단 backend.md.api_contract.exclude_paths 매칭은 제외
  method_match:
    - 라우트 (method, path) 와 fragment 가 다르면 → critical
  auth_match:
    - 라우트의 guard decorator vs fragment.security 다르면 → warning
  request_schema_compatibility:
    - first-class framework + DTO 추출 가능 시: DTO 필드 vs schema 필드 차이 → warning
    - first-class 외: schema 검사 skip + info ("manual TODO")

검사 항목 — drift report 신선도:
  drift_report_freshness:
    - .backflow/api-contract-drift.md 의 timestamp 가 openapi.yaml mtime 보다 오래 전이면 → warning ("export 후 drift report 미생성")
  drift_critical_unresolved:
    - drift_report 의 critical 행이 0 이 아니면 → critical (사용자 정정 필요)

검사 항목 — generated marker:
  - openapi.yaml 첫 줄에 "AUTO-GENERATED by backflow:export-api-contract" 주석 없으면 → warning
  - openapi.yaml.info.version / contractHash 가 비어있으면 → warning

예외:
  - source: ts-only 시 라우트 검사 항목 전부 skip + info 메시지
  - TS §3.2 누락 (grace) + openapi.yaml 부재 → drift 검사 전체 skip + warning ("§3.2 미작성, grace mode")
```

#### Frontflow §9 (`frontflow:validate-code` 추가) — critical

```yaml
입력:
  openapi_file: frontend.md.api_contract.source (모노레포 상대경로 또는 캐시 경로)
  lock_file: frontend.md.api_contract.contract_lock_file (.frontflow/api-contract.lock)
  generated_dir: frontend.md.api_contract.client_dir (예: src/api/generated)
  types_file: frontend.md.api_contract.types_file
  msw_handlers_file: frontend.md.api_contract.msw_handlers_file (emit_msw=true 시)
  api_dir: src/api (impl-api-integration 출력 — client.ts 등)

검사 항목 — version/hash 박제 일관성:
  lock_version_match:
    - .frontflow/api-contract.lock.version != openapi.yaml.info.version → critical (sync-api-client 재실행 필요)
  lock_hash_match:
    - .frontflow/api-contract.lock.contract_hash != openapi.yaml 의 재계산 hash → critical
  header_marker_match:
    - generated 파일 헤더의 박제 version/hash 가 lock 과 다르면 → critical (수동 수정 의심)

검사 항목 — generated 파일 무결성:
  generated_marker:
    - generated_dir 의 모든 파일에 "AUTO-GENERATED" 주석 없으면 → warning
  manual_edit_detection:
    - generated 파일에 `// EDITED:` / `// MANUAL:` 같은 주석 발견 → critical (재생성 시 손실)
  orphan_in_generated:
    - generated_dir 에 있는 operationId 가 openapi.yaml.paths 어디에도 없으면 → critical (stale)
  missing_in_generated:
    - openapi.yaml.operationId 중 generated 에 없는 것 → critical (불완전 codegen)

검사 항목 — types.gen.ts 일관성:
  errorcode_enum_match:
    - types.gen.ts 의 ErrorCode union 이 openapi.yaml.components.schemas.ErrorCode.enum 과 1:1 → 불일치 시 critical
  schema_count_match:
    - types.gen.ts 의 export 된 type 개수 (대략적) 가 openapi.yaml.components.schemas 보다 적으면 → warning

검사 항목 — MSW 핸들러 (emit_msw=true 시):
  msw_path_coverage:
    - openapi.yaml.paths 의 모든 (method, path) 가 handlers.gen.ts 에 등장 → 누락 시 warning
  msw_response_status:
    - handlers.gen.ts 의 응답 status 가 openapi.yaml.responses.{status} 의 키와 일치 → 불일치 시 warning

검사 항목 — hand-written 잔존 검출:
  duplicate_api_function:
    - api_dir/*.ts (생성 디렉토리 외) 에서 generated 함수와 같은 이름 export → critical (impl-api-integration housekeeping 미적용)
  duplicate_api_type:
    - api_dir 외부에서 EnrollRequest 같은 schema 명을 다시 export → warning (types.gen.ts import 권장)

예외:
  - lock_file 부재 (첫 sync 전) → 모든 lock 검사 skip + warning ("api-contract.lock 부재 — sync-api-client 미실행")
  - generator: manual 시 emit_msw / emit_query_keys 검사 자동 skip
```

## 5. 출력 파일 예시

### 5.1 Backend `openapi/openapi.yaml` (export 결과)

```yaml
# AUTO-GENERATED by backflow:export-api-contract from specs/TS-2026-001.md §3.2 + §4
# Re-run the skill to regenerate. Manual edits trigger validate-code critical.
# info.version: bump on contract surface change only.
# contractHash: sha256 of sorted serialization of paths + schemas + securitySchemes.

openapi: 3.1.0
info:
  title: speaker-service
  version: 0.3.0
  description: AUTO-GENERATED — see specs/TS-2026-001.md
  x-contract-hash: 7f3b2a1c8d5e4f6b9c0a1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a
servers:
  - url: /api/v1
paths:
  /speakers/enroll:
    post:
      operationId: enrollSpeaker
      summary: 화자 등록
      tags: [speakers]
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              $ref: '#/components/schemas/EnrollRequest'
      responses:
        '201':
          description: created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/EnrollResponse'
        '400':
          $ref: '#/components/responses/AUDIO_TOO_SHORT'
        '409':
          $ref: '#/components/responses/SPEAKER_DUPLICATE_NAME'
components:
  schemas:
    EnrollRequest: { ... }
    EnrollResponse: { ... }
    EmbeddingStatus: { ... }
    ErrorCode:
      type: string
      enum:
        - AUDIO_TOO_SHORT
        - SPEAKER_DUPLICATE_NAME
        - AUTH_INVALID_CREDENTIALS
        - AUTH_TOKEN_EXPIRED
        - SYSTEM_INTERNAL_ERROR
    ErrorEnvelope:
      type: object
      required: [error]
      properties:
        error:
          type: object
          required: [code, message]
          properties:
            code: { $ref: '#/components/schemas/ErrorCode' }
            message: { type: string }
            meta: { type: object, additionalProperties: true }
  responses:
    # AUTO-INJECTED from §4 에러 코드 맵
    AUDIO_TOO_SHORT:
      description: '오디오 파일이 너무 짧음'
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorEnvelope' }
          example:
            error:
              code: AUDIO_TOO_SHORT
              message: 오디오 파일이 너무 짧습니다 (최소 3초)
    SPEAKER_DUPLICATE_NAME:
      description: '같은 이름의 화자가 이미 존재'
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorEnvelope' }
          example:
            error:
              code: SPEAKER_DUPLICATE_NAME
              message: 같은 이름의 화자가 이미 존재합니다
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

### 5.2 Backend `.backflow/api-contract-drift.md` (export 결과)

```markdown
# API Contract Drift Report

> Generated: 2026-04-26 14:22:01 by backflow:export-api-contract
> Compared: TS-2026-001 §3.2 + §4 vs src/controllers/
> source mode: ts-and-routes
> framework confidence: high (NestJS first-class)

## Summary
- TS endpoints: 12
- Route endpoints: 13
- Drift findings: 2

## Findings

### 1. Route exists but TS missing — critical
- Route: `POST /speakers/{id}/embedding-redo`
- File: `src/controllers/speakers.controller.ts:87`
- Action: TS §3.2 에 추가하거나 컨트롤러 라우트 제거. 의도된 internal endpoint 면 `backend.md.api_contract.exclude_paths` 추가

### 2. Schema mismatch — warning
- Endpoint: `POST /speakers/enroll`
- Field: `name`
- TS §3.2: `{ type: string, maxLength: 64 }`
- Route DTO: `name: string` (no length validation)
- Action: DTO 에 `@MaxLength(64)` 추가 (class-validator), 또는 TS 에서 maxLength 제거
```

### 5.3 Frontend `src/api/generated/speakers.ts` (codegen 결과)

```typescript
// AUTO-GENERATED by frontflow:sync-api-client
// from openapi/openapi.yaml@info.version=0.3.0 contractHash=7f3b2a1c8d5e...
// Re-run the skill to regenerate. Manual edits trigger validate-code critical.
// generator: openapi-typescript-codegen

import { client } from '../client';
import type { EnrollRequest, EnrollResponse } from '../types.gen';

export async function enrollSpeaker(body: EnrollRequest): Promise<EnrollResponse> {
  const formData = new FormData();
  formData.append('name', body.name);
  formData.append('audio_file', body.audio_file);
  formData.append('workspace_id', body.workspace_id);
  return client.post('/speakers/enroll', formData);
}

export async function listSpeakers(workspaceId: string): Promise<SpeakerListResponse> {
  return client.get('/speakers', { params: { workspace_id: workspaceId } });
}

// Query keys (emit_query_keys=true)
export const speakerKeys = {
  all: ['speakers'] as const,
  list: (workspaceId: string) => [...speakerKeys.all, 'list', workspaceId] as const,
  detail: (id: string) => [...speakerKeys.all, 'detail', id] as const,
};
```

### 5.4 Frontend `src/api/types.gen.ts`

```typescript
// AUTO-GENERATED by frontflow:sync-api-client
// from openapi/openapi.yaml@info.version=0.3.0 contractHash=7f3b2a1c8d5e...

export interface EnrollRequest {
  name: string;
  audio_file: File;
  workspace_id: string;
}

export interface EnrollResponse {
  speaker_id: string;
  name: string;
  embedding_status: EmbeddingStatus;
  created_at: string;
}

export type EmbeddingStatus = 'pending' | 'processing' | 'ready' | 'failed';

// XR-003: ErrorCode union 은 OpenAPI components.schemas.ErrorCode.enum 과 1:1
export type ErrorCode =
  | 'AUDIO_TOO_SHORT'
  | 'SPEAKER_DUPLICATE_NAME'
  | 'AUTH_INVALID_CREDENTIALS'
  | 'AUTH_TOKEN_EXPIRED'
  | 'SYSTEM_INTERNAL_ERROR';

export interface ErrorEnvelope {
  error: {
    code: ErrorCode;
    message: string;
    meta?: Record<string, unknown>;
  };
}
```

### 5.5 Frontend `.frontflow/api-contract.lock`

```json
{
  "version": "0.3.0",
  "contract_hash": "7f3b2a1c8d5e4f6b9c0a1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a",
  "source_etag": "\"abc123def456\"",
  "generated_at": "2026-04-26T14:22:33Z",
  "generator": "openapi-typescript-codegen",
  "generator_version": "0.27.0"
}
```

### 5.6 Frontend `src/mocks/handlers.gen.ts` (emit_msw=true)

```typescript
// AUTO-GENERATED by frontflow:sync-api-client
// from openapi/openapi.yaml@info.version=0.3.0 contractHash=7f3b2a1c8d5e...
import { http, HttpResponse } from 'msw';

export const handlers = [
  http.post('/api/v1/speakers/enroll', () =>
    HttpResponse.json({
      speaker_id: '00000000-0000-0000-0000-000000000001',
      name: '홍길동',
      embedding_status: 'pending',
      created_at: '2026-04-26T00:00:00Z',
    }, { status: 201 })
  ),
  http.get('/api/v1/speakers', () =>
    HttpResponse.json({ items: [], total: 0 })
  ),
];
```

### 5.7 Frontend `src/api/client.ts` (사람 작성 — impl-api-integration 책임)

```typescript
// 사람 작성. impl-api-integration 가 frontend.md.api_client.method 에 따라 골격 생성
import axios from 'axios';
import { handleError } from '@/errors/handler';

export const client = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL,
  withCredentials: true,
});

client.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const apiError = err.response?.data?.error ?? { code: 'NETWORK_TIMEOUT', message: err.message };
    const decision = handleError(apiError);
    return Promise.reject(decision);
  },
);
```

## 6. 마이그레이션 — 기존 프로젝트

### 6.1 Scenario A — 신규 프로젝트
- TS §3.2 작성됨 → `export-api-contract` 가 fragment 에 §4 합성해 export (라우트 미존재 시 `source: ts-only`)
- 프론트엔드도 신규 → `sync-api-client` 가 처음부터 codegen + lock 파일 생성
- 이후 라우트 구현 후 `source: ts-and-routes` 로 전환

### 6.2 Scenario B — 백엔드 라우트 있고 TS §3.2 없음 (legacy, XR-002 강화)
1. `backend.md.framework.language` 가 first-class (TypeScript Node) 인지 확인. 그 외는 routes-only 모드 권장하지 않음 (`ts-only` + 수기 작성 권고)
2. `export-api-contract --source routes-only` 로 라우트에서 fragment **초안** 생성. drift 리포트에 신뢰도 등급(`high`/`medium`/`low`) 명시:
   - **high**: NestJS/Fastify 등 schema 추출 가능 — 초안 그대로 유용
   - **medium**: Express path/method 만 추출, schema 는 `# manual TODO` 마커
   - **low**: heuristic 만 — 사람 review 필수
3. 사용자가 초안을 검토해 `specflow:revise` 로 TS §3.2 에 이식 (특히 medium/low 는 schema 보강 필수)
4. `export-api-contract --source ts-and-routes` 정식 모드 전환
5. routes-only 모드는 **일회성** — `backend.md` 에 영구 저장 시 warning

### 6.3 Scenario C — 프론트엔드에 hand-written 클라이언트가 이미 있음
1. `sync-api-client --dry-run` 으로 generated 파일 미리보기
2. 기존 `src/api/*.ts` 와 충돌하는 파일 목록 표시
3. 사용자 확인 후:
   - **Option 1 (권장)**: 기존 파일을 `frontflow:impl-api-integration` 책임 영역으로 축소 (client.ts + 비즈니스 와이어링만), generated 파일은 별도 디렉토리
   - **Option 2**: 기존 파일을 generated 로 대체. 호출처가 sync 결과 함수를 import 하도록 codemod
4. MSW 가 이미 있으면 `emit_msw: false` 로 두고 기존 핸들러 보존
5. validate-code §9 frontend 의 `duplicate_api_function` 검사가 잔존 hand-written 함수를 critical 로 보고

### 6.4 Scenario D — 모노레포 별 구조
- 백엔드와 프론트엔드가 같은 git repo 다른 워크스페이스: `frontend.md.api_contract.source` 를 `../backend/openapi/openapi.yaml` (상대경로)
- 별도 repo: backend 가 `openapi/openapi.yaml` 을 release artifact 로 publish (GitHub release / S3 / CDN), frontend 는 URL 로 fetch
- 양쪽 모두 `info.version` + `contractHash` 박제 + `.frontflow/api-contract.lock` 로 stale 검출

## 7. CONTRACTS.md 갱신 필요 사항

이 skill 추가 시 같은 PR/커밋에서 동반:

- `plugins/backflow/CONTRACTS.md`
  - 실행 순서 다이어그램에 `export-api-contract` 노드 추가 (`impl-integrations` 후, `generate-tests` 와 병렬)
  - 스킬별 계약 섹션에 `export-api-contract` 카드 (책임: components 합성 명시)
  - 공통 레지스트리 테이블에 `backend.md.api_contract.*` 키 그룹 행 추가
  - specflow 역매핑 테이블에 "TS §3.2 OpenAPI fragment → export-api-contract", "TS §4 에러 코드 맵 → export-api-contract (components 합성)" 추가
  - 출력 artifact 테이블에 `openapi/openapi.yaml`, `.backflow/api-contract-drift.md` 추가
- `plugins/frontflow/CONTRACTS.md`
  - 실행 순서 다이어그램에 `sync-api-client` 추가 (`impl-error-handling` 후, `impl-api-integration` 앞)
  - 스킬별 계약 섹션에 `sync-api-client` 카드
  - `impl-api-integration` 카드 갱신 — codegen 출력 import 책임 명시 (Notes 섹션)
  - specflow 역매핑 테이블에서 "TS §API 설계 → impl-api-integration" 행을 "→ sync-api-client (codegen) + impl-api-integration (wiring)" 으로 분리
  - 공통 레지스트리에 `.frontflow/api-contract.lock` 추가
- `plugins/specflow/skills/validate/rules/ts-rules.md` 신규 룰 40~49 (47 만 critical, 나머지 warning grace)
- `plugins/frontflow/skills/impl-api-integration/SKILL.common.md` 책임 축소 — codegen 결과를 import 하도록 prompt 정리

## 8. 오픈 질문 / Future work

- **API 버저닝 (v1/v2 병존)** — Phase 2 (`backflow:impl-api-versioning`). multiple `openapi/v1.yaml` / `v2.yaml` 권장
- **Deprecation 경로** — OpenAPI 의 `deprecated: true` flag + Sunset 헤더. Phase 2
- **tRPC 어댑터** — Phase 2 — `backflow:export-trpc-router` + `frontflow:sync-trpc-client`
- **gRPC / protobuf** — 별도 schema 파이프. Phase 2
- **GraphQL** — `apollo-codegen` 같은 기존 도구 활용. Phase 2 어댑터
- **AsyncAPI (SSE/WebSocket/MQ)** — Phase 2. 현재는 OpenAPI `text/event-stream` content-type 으로 SSE 만 처리
- **OpenAPI 3.0 다운컨버트** — `format` 옵션 확장. Phase 2 도구 호환용
- **Annotation-first read** — nestjs/swagger / drf-spectacular 의 metadata 를 export 시 *읽기만* 보강. (a) 와는 다름 — TS 가 여전히 source. Phase 2 옵션
- **Contract test (Pact)** — 생성된 OpenAPI 를 Pact provider state 로 변환. Phase 2
- **Mock backend (prism)** — Phase 2 (`backflow:impl-mock-server`)
- **Backend response envelope 자동 검출** — 정상 응답 envelope (`{success, data}`) 자동 wrap 옵션. Phase 2
- **OpenAPI to ADR 역참조** — fragment 내부에 `x-ts-adr: ADR-003` extension. Phase 2
- **CI integration** — `export-api-contract --check` / `sync-api-client --check` GitHub Actions step templating. Phase 3
- **runtime_assertion 본격 지원** — `x-api-version` 헤더 응답 + frontend 비교. Phase 2 안정화
- **Generator 다양화** — `orval`, `openapi-zod-client` Phase 2 stable 지원. queryKey/zod 검증 first-class 화

## 9. 완료 기준 (Definition of Done)

### Phase 1 (3) "ship" 조건

- [ ] `specflow:generate-ts` 가 §3.2 OpenAPI fragment 부속섹션 포함해 출력 (canonical path, ErrorEnvelope $ref, components.responses 비움)
- [ ] `specflow:validate` ts-rules 40~49 추가 (47 critical, 나머지 warning grace)
- [ ] `backflow:export-api-contract` 실행 시 `openapi/openapi.yaml` 생성 — **`components.schemas.ErrorCode` enum 채움 + `components.responses` 합성** + `info.version` + `contractHash` 박제 + `.backflow/api-contract-drift.md` 작성
- [ ] `backend.md.api_contract.*` 신규 키 추가 (source / output_path / format / servers / drift_report_path / exclude_paths / contract_hash_alg)
- [ ] export-api-contract 가 first-class framework (NestJS/Express/Fastify) 에서 라우트 추출 동작. 그 외 graceful 부분 추출 + 신뢰도 등급 출력
- [ ] `frontflow:sync-api-client` 실행 시 `src/api/generated/*` + `src/api/types.gen.ts` + (옵션) `src/mocks/handlers.gen.ts` + **`.frontflow/api-contract.lock`** 생성. 헤더에 version+hash 박제
- [ ] `frontend.md.api_contract.*` 신규 키 추가 (source / generator / client_dir / types_file / msw_handlers_file / emit_msw / emit_query_keys / pinned_version / contract_lock_file / runtime_assertion)
- [ ] `frontflow:impl-api-integration` SKILL prompt 정리 — codegen 결과 import + 비즈니스 와이어링만 책임. 클라이언트 함수 hand-write 안내문 제거
- [ ] `backflow:validate-code` §9 + `frontflow:validate-code` §9 drift 룰 추가 (양 방향 hash drift)
- [ ] `backflow/CONTRACTS.md` + `frontflow/CONTRACTS.md` 갱신
- [ ] 최소 1개 실프로젝트 E2E — TS §3.2 작성 → export → sync → frontend codegen 사용 확인 + drift 시뮬레이션 (TS 변경 후 export 안 함 → validate critical)

### "stable" 조건

- 2개 이상 프로젝트에서 실사용
- Scenario A/B/C/D 마이그레이션 각각 최소 1회 성공
- TS-rules 40~46, 48, 49 grace → critical 승격
- generator 옵션 중 추가 1개(`orval` 또는 `openapi-zod-client`) Phase 2 에서 stable 검증
- first-class 외 framework (FastAPI / Spring Boot) Phase 2 에서 등급 격상

## 10. 다음 작업 (이 설계 문서 머지 후)

Phase 1 (1)·(2) 와 동일한 4-step 패턴 + B' 추가:

1. **Task A** — `specflow:generate-ts` 프롬프트 + template + ts-rules 40~49 추가
2. **Task B** — `backflow:export-api-contract` skill 신설 + `backend.md.api_contract.*` 섹션 + `backflow/CONTRACTS.md` 갱신 (특히 components 합성 책임)
3. **Task B'** — `frontflow:sync-api-client` skill 신설 + `frontend.md.api_contract.*` 섹션 + `.frontflow/api-contract.lock` 도입 + `frontflow/CONTRACTS.md` 갱신
4. **Task C** — `frontflow:impl-api-integration` 책임 축소 housekeeping (codegen 출력 import 명시)
5. **Task D** — `backflow:validate-code` + `frontflow:validate-code` §9 drift 룰 (본 문서 §4.4 의 YAML 블록을 SKILL 에 그대로 이식)

Phase 1 (3) 전체 예상 5 commit (B/B' 묶으면 4 commit), 1~2주 소요.
