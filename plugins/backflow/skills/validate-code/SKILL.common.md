---
name: validate-code
description: 생성된 백엔드 코드의 품질을 검증합니다. "코드 검증", "코드 리뷰" 요청 시 사용.
argument-hint: [검증할 파일 또는 디렉토리 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 코드 품질 검증 (BV1)

ultrathink

생성된 백엔드 코드가 프로젝트 컨벤션과 품질 기준을 충족하는지 검증합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md)
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면)

## 입력

$ARGUMENTS 의 파일/디렉토리를 Read/Glob으로 읽으세요.

## ★ frontflow FV1과 동일한 비격리 원칙 ★

코드 검증은 "어떤 서비스를 어떤 맥락에서 만들었는지"를 알아야 정확합니다.
specflow V 스킬처럼 `context: fork`하지 않습니다.

## 검증 항목

### 1. 컨벤션 준수 (critical)

```yaml
파일 위치:
  - 엔티티가 backend.md의 entity_dir 하위에 있는가
  - 서비스가 service_dir 하위에 있는가
  - 컨트롤러가 controller_dir 하위에 있는가
  - module_pattern(flat/feature-module/domain-driven)과 일치하는가

네이밍:
  - 파일명이 backend.md의 naming 컨벤션을 따르는가
  - 클래스명이 파일명과 일치하는가 (speaker.service.ts → SpeakerService)

구조:
  - 계층 분리: 컨트롤러→서비스→리포지토리 방향으로만 의존
  - 순환 의존 = 0건
  - 리포지토리가 서비스를, 서비스가 컨트롤러를 import하지 않는가
```

### 2. 계층 경계 (critical)

```yaml
컨트롤러 침범:
  - 컨트롤러에 비즈니스 로직(조건 분기, 계산)이 있는가
  - 컨트롤러에서 리포지토리를 직접 호출하는가

서비스 침범:
  - 서비스에 HTTP 관심사(상태 코드, 헤더, 쿠키)가 있는가
  - 서비스에서 Request/Response 객체에 접근하는가

리포지토리 침범:
  - 리포지토리에 비즈니스 로직이 있는가
  - 리포지토리에서 다른 리포지토리를 직접 호출하는가

맵 대조 (task-file-map.md 있을 때):
  - 생성/수정된 파일이 맵에 선언된 파일과 일치하는가
  - 맵의 responsibility.should_not에 해당하는 코드가 파일에 없는가
  - 맵에 없는 파일이 생성되지 않았는가
```

### 3. 에러 핸들링 (critical)

```yaml
- 서비스의 모든 실패 경로에 적절한 에러 throw가 있는가
- try-catch에서 에러를 삼키지(swallow) 않는가
- 빈 catch 블록 = 0건
- 외부 호출에 타임아웃이 있는가
```

### 4. 타입 안전성 (critical)

```yaml
- any 사용 = 0건
- as 타입 단언 최소화
- DTO 필드 타입이 TS 명세서 스키마와 일치하는가
- nullable 처리가 명시적인가
```

### 5. 보안 (critical)

```yaml
- SQL injection 가능성 (raw 쿼리에 문자열 보간) = 0건
- 비밀번호/토큰의 평문 로깅 = 0건
- 사용자 입력의 검증 없는 사용 = 0건
- 민감 데이터가 응답에 노출되지 않는가
```

### 6. 테스트 가능성 (warning)

```yaml
- 의존성이 주입 가능한가 (new로 직접 생성하지 않는가)
- 외부 서비스가 인터페이스/추상화를 통해 접근되는가
- 테스트에서 목(mock) 교체가 가능한 구조인가
```

### 8. 관측성 계약 drift (critical) — Phase 1 (2)

`backflow:impl-observability` 가 생성한 산출물이 TS §7.1 관측성과 일치하는지 검사. 실 로그·trace 출력에 required_tags 가 모두 등장하는지, sensitive_field_masking 이 redact 에 반영됐는지 등. (참고: §7 에러 코드 drift 룰 아래에 위치하나 numerical ID 는 8 — 룰 ID 는 안정적, 파일 위치는 추후 정리.)

```yaml
입력:
  context_file: backend.md.observability.context_file (예: src/observability/context.ts)
  logger_file: backend.md.observability.logger_file (예: src/observability/logger.ts)
  request_id_middleware_file: backend.md.observability.request_id_middleware_file
  tracing_file: backend.md.observability.tracing_file
  error_tag_file: backend.md.observability.error_tag_file (error_code_tag=true 시)
  bootstrap_file: backend.md.observability.bootstrap_file (예: src/main.ts)
  ts_section: specs/TS-*.md §7.1 관측성

검사 항목 — 로깅:
  required_tags_in_logger:
    - logger_file 의 formatter 출력에 TS §7.1 required_tags 의 모든 키(service, environment, request_id, trace_id 등) 가 등장하지 않으면 → critical
    - "request_id" 가 logger formatter 에 있으나 context_file (AsyncLocalStorage 등) 와 연결되지 않으면 → critical (실 로그에 빈 값으로 나옴)
  sensitive_masking:
    - TS §7.1 sensitive_field_masking 의 모든 패턴이 logger redact (또는 winston format / structlog processor) 에 등장하지 않으면 → critical
  log_format:
    - logger 가 json 출력을 보장하지 않으면 → warning (text 는 dev only)
  log_level:
    - logger init 이 process.env[log_level_env] 또는 동등한 메커니즘으로 LOG_LEVEL 을 읽지 않으면 → warning

검사 항목 — 트레이싱:
  sampling_rate:
    - tracing_file 에 sampling_rate_dev / sampling_rate_prod 가 env 분기로 적용되지 않으면 → critical
    - sampling_rate_prod > 0.5 이면서 production 로 보이는 코드 경로면 → warning ("운영 트래픽에서 비용 폭증 가능")
  otlp_endpoint_env:
    - exporter URL 이 하드코딩 (`http://...` 리터럴) 이면 → critical (env 변수 사용 강제)
  resource_attributes:
    - service_name / deployment.environment 가 OTel resource 에 등록되지 않으면 → warning

검사 항목 — Middleware / Bootstrap:
  middleware_registered:
    - request_id_middleware_file 가 존재하는데 bootstrap_file (또는 framework convention 진입점) 에 등록되지 않으면 → critical
  tracing_first_import:
    - bootstrap_file 의 import 순서에서 tracing_file 이 첫 번째가 아니면 → critical (auto-instrumentation 누락)
  traceparent_passthrough:
    - middleware 가 incoming `traceparent` 헤더를 OTel context 에 추출하지 않으면 → critical (분산 추적 끊김)
  correlation_header:
    - middleware 가 backend.md.observability.correlation_header 값을 사용하지 않거나 응답 헤더로 echo 하지 않으면 → warning

검사 항목 — ErrorMeta hook:
  error_tag_present:
    - error_code_tag=true 이고 §4 에러 코드 맵 비어있지 않은데 error_tag_file 부재 → critical
    - error_code_tag=false 인데 error_tag_file 존재 → warning ("의도치 않은 hook 활성화")
  app_exception_filter_calls:
    - AppExceptionFilter (impl-middleware 출력) 가 tagError 를 import 하지 않거나 catch() 에서 호출하지 않으면 → critical (관측성 hook 무력화)
  errormeta_import_path:
    - error_tag_file 의 ErrorMeta import 가 backend.md.error_handling.error_code_enum 과 일치하지 않으면 → critical

검사 항목 — 비표준 로그 호출 검출:
  console_log_remaining:
    - 프로젝트 코드에서 `console.log(`, `console.warn(`, `console.error(`, `console.debug(`, `console.info(` → critical
    - 단 logger.ts / context.ts / tracing.ts 등 관측성 파일 자체는 예외 (debug 용 console 허용)
  print_statements:
    - Python: `print(`, `sys.stdout.write` (logger 모듈 외) → critical
    - Java: `System.out.println`, `System.err.println` → critical
    - Go: `fmt.Println`, `fmt.Printf` (main 외) → critical
    - Rust: `println!`, `eprintln!` (main / examples 외) → warning

검사 항목 — Vendor leakage (계약 핵심):
  vendor_name_in_code:
    - 생성 코드에 `datadog`, `dd-trace`, `newrelic`, `sentry`, `honeycomb`, `appdynamics`, `dynatrace` 등 벤더명 등장 → critical
    - "OTel only" 계약 위반. exporter URL 은 env 로만 결정.

generated_marker:
  - context.ts / logger.ts / tracing.ts / error-tag.ts 에 "AUTO-GENERATED" 주석 없으면 → warning

env 변수:
  - .env.example 에 OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_SERVICE_NAME / LOG_LEVEL 누락 시 → warning

예외:
  - TS §7.1 부재 (grace mode) 이고 logger/tracing 파일이 default 5종 코드만 가지면 drift 검사 스킵 + 단일 warning ("§7.1 미작성, grace mode")
  - Scenario D (기존 OTel init 보존) 시 tracing.ts 가 skill 출력이 아닐 수 있음. backend.md.observability.tracing_file 가 명시적으로 "external" 이면 tracing 검사 스킵 + info 메시지
```

### 7. 에러 코드 계약 drift (critical) — Phase 1 (1)

`backflow:impl-error-codes` 가 생성한 산출물이 TS §4 에러 코드 맵과 일치하는지 검사. **양방향**으로 비교한다 — 한쪽에만 있는 코드는 모두 finding 으로 보고.

```yaml
입력:
  codes_file: backend.md.error_handling.error_code_enum (예: src/errors/codes.ts)
  http_mapping_file: backend.md.error_handling.http_mapping_file
  i18n_output_dir: backend.md.error_handling.i18n_output_dir
  ts_section: specs/TS-*.md §4 에러 코드 맵 (자동 탐지; 여러 TS 가 있으면 합집합)

검사 항목:
  missing_in_code:
    - TS §4 행에 있으나 codes.ts ErrorCode enum 에 없는 code → critical
    - 권고: impl-error-codes 재실행
  orphan_in_code:
    - codes.ts ErrorCode 에 있으나 TS §4 어느 행에도 없는 code → critical
    - 권고: TS 에 추가하거나 코드에서 제거 (의도적 예약이면 주석 + 별도 화이트리스트)
  http_status_mismatch:
    - codes.ts ErrorMeta[code].httpStatus !== TS row.http_status → critical
  i18n_key_mismatch:
    - codes.ts ErrorMeta[code].i18nKey !== TS row.i18n_key → critical
  http_mapping_consistency:
    - HTTP_STATUS_MAP 의 키 집합 ≠ ErrorCode 키 집합 → critical
    - HTTP_STATUS_MAP[code] !== ErrorMeta[code].httpStatus → critical
  i18n_locale_files:
    - error_handling.i18n_enabled=true 시:
        languages 배열의 각 lang 에 대해 {i18n_output_dir}/errors.{lang}.json 존재 → warning
        JSON 의 i18nKey 집합 ⊇ ErrorMeta 의 i18nKey 집합 → warning
  generated_marker:
    - codes.ts 첫 줄에 "AUTO-GENERATED" 주석 없으면 → warning (사람 편집 의심)

예외:
  - TS §4 가 비어있고 codes.ts 가 grace-period 기본 5 코드(AUTH_UNAUTHORIZED,
    AUTH_FORBIDDEN, VALIDATION_FAILED, SYSTEM_INTERNAL_ERROR, NETWORK_TIMEOUT) 만
    가지고 있으면 drift 검사 스킵 + 단일 warning ("§4 미작성, grace mode")
```

### 9. API 계약 drift (critical) — Phase 1 (3)

`backflow:export-api-contract` 가 생성한 `openapi/openapi.yaml` 이 TS §3.2 + §4 + 실제 라우트와 일치하는지 검사.

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

### 10. 파일 업로드 drift (critical) — Phase 1 (5)

`backflow:impl-file-upload` 가 생성한 controller / service / meta / storage adapter 가 TS §9 + 선행 skill 출력과 일치하는지 검사.

```yaml
입력:
  ts_section: specs/TS-*.md §9 파일 처리
  service_registry: .backflow/service-registry.md
  uploads_dir: backend.md.file_upload.uploads_module_dir
  storage_dir: uploads_dir + "/" + backend.md.file_upload.storage_subdir
  selected_storage_file: storage_dir + "/" + backend.md.file_upload.selected_storage_filename
  vendor: backend.md.file_upload.storage_vendor
  resize_dir: uploads_dir + "/" + backend.md.file_upload.resize_subdir
  resize_presets: backend.md.file_upload.resize_presets
  metadata_schema_version: backend.md.file_upload.metadata_schema_version

§10.1 — TS §9 ↔ controller/service 일관성:
  upload_kind_in_controller:
    - TS §9 의 모든 upload_kind 가 controller 핸들러/디렉토리/operationId 에 등장 → 누락 시 critical
  mime_validation:
    - controller/service/DTO 의 mime_type 검증이 §9.mime_types 와 1:1 → 불일치 시 critical
  max_size_validation:
    - server 측 size 검증이 §9.max_size_mb * 1024 * 1024 와 일치 → 불일치 시 critical
  server_side_head_recheck:
    - complete handler 가 storage.head() 또는 동등한 호출로 size/mime 재검증 → 누락 시 critical
    - client 의 size_bytes / mime_type 만 사용해 status: complete 전이 → critical
  storage_path_resolution:
    - storage_path 의 모든 placeholder 가 reserved (file_id/ext/upload_kind) 또는 명시된 source ({key:auth}/{key:body}/{key:path}) 에서 resolve → 미해결 시 critical
    - controller 의 path resolve 로직이 source 별로 분기되었는가 (req.user / req.body / req.params) → 분기 부재 시 critical
    - source 표기 없이 사용된 custom placeholder → warning ("source 명시 권고; body default 적용 중")
  related_error_codes:
    - TS §4 에 FILE_TOO_LARGE / MIME_NOT_ALLOWED / STORAGE_UNAVAILABLE / FILE_INTEGRITY_MISMATCH / FILE_NOT_FOUND 부재 → warning

§10.2 — Vendor 식별자 영역 검사:
  vendor_identifier_in_uploads:
    - controller/service/module/DTO/storage/types.ts/storage/local.ts 에 vendor SDK import (`@aws-sdk/`, `@google-cloud/storage`, `aws-sdk`, `Minio`) 또는 vendor 직접 호출 등장 → critical
  selected_storage_static_export_only:
    - selected-storage.ts 가 단일 `export { X as storage } from './Y'` 외 형태(런타임 if/switch / 다중 import / 동적 import / SDK direct import) → critical
    - vendor != "" 이면 X 가 vendor adapter 의 export 와 일치 → 불일치 시 critical
    - vendor == "" 이면 X 가 localAdapter → 불일치 시 critical
    - **selected-storage.ts 자체의 vendor 이름 (s3Adapter, gcsAdapter 등) 은 허용** — re-export 만 검사
  storage_directory_exempt:
    - storage/{vendor}.ts 는 vendor 식별자 검사 제외 + info
  local_passthrough_guard:
    - storage_vendor != "" 일 때 local-passthrough route 등록 → critical (production 노출 위험)
    - storage_vendor == "" + NODE_ENV !== 'production' 가드 부재 → critical
    - local passthrough 가 query path 직접 사용 (file_id 기반 server-side 재계산 미사용) → critical
  local_passthrough_auth:
    - local passthrough route 에 auth guard / middleware 미적용 → critical
    - file_id 로 조회한 meta.owner_id 와 인증된 user_id 일치 검증 부재 → critical (XR-003)

§10.3 — 메타 entity 일관성:
  meta_required_fields:
    - id / upload_kind / storage_path / mime_type / size_bytes / status / metadata_schema_version / metadata 모두 존재 → 누락 시 critical
  status_enum_match:
    - status enum 이 [pending, complete, failed, expired] → 추가/누락 시 warning
  retention_handling:
    - §9.retention_days > 0 인 upload_kind 가 있는데 expires_at 부재 → warning
  metadata_schema_version_field:
    - metadata 에 schema_version: 1 (또는 entity 별도 컬럼) 부재 → warning
  metadata_canonical_shape:
    - metadata.original = { path, size_bytes, mime_type } 패턴 service 코드 사용 → 미사용 시 warning
    - variants 가 있는 upload_kind 의 metadata.variants[variant] = { path, width, height, mime_type, size_bytes, status } → 미사용 시 warning

§10.4 — 리사이즈 일관성 (central/per-variant 둘 다):
  resize_handler_present:
    - §9 의 모든 resize_variants 에 대해:
      - resize_worker_pattern: per-variant — resize/{variant}.processor.ts 존재 → 누락 시 warning
      - resize_worker_pattern: central — central worker 의 preset key dispatch 분기에 variant 등장 → 누락 시 warning
  preset_lookup:
    - resize 코드의 preset key 가 backend.md.file_upload.resize_presets 미정의 → critical
  preset_consistency:
    - §9 의 resize_variants 가 resize_presets 에 정의 → 누락 시 warning ("preset 추가 권고")
  enqueue_on_complete:
    - complete handler 가 variants 가 있는 upload_kind 에서 리사이즈 enqueue 호출 → 누락 시 warning

§10.5 — 선행 skill 책임 경계:
  controller_no_duplication:
    - **사전 조건**: .backflow/service-registry.md 또는 .backflow/controller-registry.md 에 controller 의 operationId / generated_by 추적 정보 존재 시에만 정밀 검사
    - 추적 정보 부재 시: 휴리스틱 검사 — controller 파일에서 §9 의 upload_kind 와 매칭되는 operationId 함수의 body 가 비어있지 않으면 (return null / pass / TODO 외 본문) → warning
    - 추적 정보 존재 시: generated_by != "impl-file-upload" 인 controller 가 §9 upload operationId 를 본문 구현 → warning
  storage_service_wrapper:
    - service-registry 에 StorageService 가 있는데 impl-file-upload 가 새 storage adapter 를 wrapping 없이 작성 → warning ("기존 service wrapper 권고")

예외:
  - TS §9 부재 (grace) + impl-file-upload 가 default `generic_file` 만 → §10 검사 skip + warning
  - vendor: "" + NODE_ENV: production 빌드 → local-passthrough route 부재가 정상
  - external_services.storage 미정의 → impl-file-upload 가 local 만 + info
```

### 11. Webhook drift (critical) — Phase 1 (6)

`backflow:impl-webhook` 가 생성한 controller / service / adapter / idempotency entity 가 TS §10 + 선행 skill 출력과 일치하는지 검사.

```yaml
입력:
  ts_section: specs/TS-*.md §10 외부 연동·Webhook
  service_registry: .backflow/service-registry.md
  webhook_dir: backend.md.webhook.webhook_module_dir
  signatures_dir: webhook_dir + "/" + backend.md.webhook.signatures_subdir
  selected_signature_file: signatures_dir + "/" + backend.md.webhook.selected_signature_filename
  idempotency_entity: backend.md.webhook.idempotency_entity_path

§11.1 — TS §10 ↔ controller/service 일관성:
  webhook_id_in_controller:
    - TS §10 모든 webhook_id 가 controller 핸들러/operationId 등장 → 누락 시 critical
  signature_alg_match / signature_header_match:
    - controller / adapter 가 사용한 alg / header 가 §10 명시값과 일치 → 불일치 시 critical
  signature_secret_env_used:
    - process.env[signature_secret_env] (또는 동등) 으로 secret 로드 → 미사용 시 critical
    - 시크릿 hardcoded → critical
  idempotency_key_extraction_grammar:
    - controller/service 의 key 추출 코드가 §10.idempotency_key_source 의 minimal grammar (header/headerParam/body/fallback) 따름 → 위반 시 critical
  raw_body_preserved:
    - framework 별 anchor 패턴 검출 (XR-006):
      - NestJS: `NestFactory.create(.., { rawBody: true })` + `@Req() req: RawBodyRequest`
      - Express: webhook route 가 `express.raw(...)` middleware 적용
      - Fastify: `addContentTypeParser` 또는 `@fastify/raw-body`
      - FastAPI: `Request.body()` await
      - Spring: `HttpServletRequest.getInputStream()` 또는 `byte[] body`
    - 위 패턴 부재 시 → critical
  related_error_codes:
    - TS §4 에 WEBHOOK_SIGNATURE_INVALID / WEBHOOK_TIMESTAMP_REPLAY / WEBHOOK_IDEMPOTENCY_KEY_MISSING / WEBHOOK_REQUEST_HASH_MISMATCH 부재 → warning
    - WEBHOOK_REPLAY_DETECTED 같은 모호한 단일 코드 사용 → warning ("XR-009: 분리 권고")

§11.2 — Sender 식별자 영역 검사 + facade:
  sender_identifier_in_layers:
    - controller / service / dispatch / signatures/types.ts / selected-signature.ts 에 sender SDK import (`stripe`, `@octokit`, `@slack/`, sender 별) 등장 → critical
  selected_signature_static_dispatch_only:
    - selected-signature.ts 가 `Record<sender, SignatureAdapter>` + `getAdapter` 외 형태 (런타임 if/switch / dynamic import / 동적 require) → critical (XR-001)
    - selected-signature.ts 자체의 sender adapter import 는 허용 (정적 dispatch facade)
    - TS §10 의 모든 sender 가 ADAPTERS 객체에 등장 → 누락 시 critical
  signature_adapter_interface_compliance:
    - signatures/{sender}.ts 가 SignatureAdapter (sender / alg / verify) 충족 → 불충족 시 critical
  none_adapter_dev_only:
    - signatures/none.ts 가 production 환경에서 활성화될 수 있는 분기 → critical
  timing_safe_compare:
    - signatures/{sender}.ts 의 직접 HMAC 비교 코드 (`===`, `Buffer.compare`, `==`) 검출 → critical (XR-004 — `crypto.timingSafeEqual` 또는 SDK 검증 API 사용 의무)
    - SDK 검증 API (`Stripe.webhooks.constructEvent` 등) 사용은 timing-safe 보장으로 통과

§11.3 — Idempotency entity & race:
  required_fields:
    - id / webhook_id / idempotency_key / request_hash / status / created_at / updated_at 모두 존재 → 누락 시 critical
  unique_constraint:
    - (webhook_id, idempotency_key) UNIQUE constraint 부재 → critical
  status_enum_match:
    - [pending, processing, complete, failed] → 추가/누락 시 warning
  insert_on_conflict_pattern:
    - controller 의 idempotency insert 가 ON CONFLICT 또는 동등 (try/catch + unique violation) 패턴 → 부재 시 critical (XR-002)
  request_hash_check:
    - 기존 행 발견 시 request_hash 비교 코드 부재 → warning ("같은 key 다른 body 검출 누락")
  replay_uses_stored_response:
    - status: complete 인 idempotency hit 시 stored response_body/status 그대로 반환 → 부재 시 critical
  duplicate_delivery_log:
    - WEBHOOK_DUPLICATE_DELIVERY info log 또는 동등 부재 → warning ("XR-009 logging 권고")

§11.4 — Middleware / 라우팅 책임 경계:
  webhook_routes_bypass_auth:
    - bypass_auth_routes 의 경로가 impl-middleware auth guard 에서 bypass → 부재 시 critical
  webhook_signature_middleware_applied:
    - bypass_auth_routes 의 경로에 signature 검증이 적용 (XR-007 framework anchor):
      - NestJS: `consumer.apply(WebhookSignatureMiddleware).forRoutes('webhooks/*')` 또는 controller-level decorator
      - Express: webhook router 의 `router.use(signatureMiddleware)`
      - Fastify: `addHook('preHandler', ...)` 또는 plugin
      - FastAPI: `Depends(verify_signature)` 또는 middleware
      - Spring: `@Component` filter / interceptor
    - 패턴 부재 시 critical
  controller_no_duplication:
    - 사전 조건: service-registry 에 controller operationId 추적 정보 존재 시 — generated_by != "impl-webhook" 가 §10 webhook 본문 구현 → warning
    - 추적 정보 부재 시: 휴리스틱 — controller 파일에서 webhook_id 매칭 핸들러 본문 비어있지 않으면 warning

§11.5 — Always-200 정책 + dispatch:
  always_200_per_webhook:
    - TS §10.always_200 컬럼 명시 시 controller/service 가 그 값 기준 분기 → 위반 시 warning
    - 미명시 시 backend.md.webhook.always_200_default 사용
  enqueue_only_dispatch:
    - controller 의 webhook handler 가 직접 비즈니스 로직 호출 (큐 enqueue 외) → critical (XR-003 — 동기 모드는 Phase 2)
    - enqueue 호출은 impl-integrations 의 큐 추상 사용 — 직접 큐 driver 호출 시 warning
  signature_failure_response:
    - 서명 검증 실패 시 401 또는 403 → 그 외 (특히 200) 시 critical
  enqueue_failure_response:
    - always_200=true 시 enqueue 실패에도 200 반환 → 그 외 critical
    - always_200=false 시 enqueue 실패 → backend.md.webhook.retry_status_code (default 503) 반환 → 불일치 시 warning

예외:
  - TS §10 부재 → §11 전체 skip + info
  - signature_alg=none 인 webhook 이 NODE_ENV=development 가드 존재 시 §11.2 none_adapter_dev_only 통과
  - bypass_auth_routes 미정의 → §11.4 webhook_routes_bypass_auth 검사 skip + warning
```

## 출력

```yaml
검증 대상: {파일/디렉토리}
검증 유형: BV1 (코드 품질)

findings:
  - id: "BV1-001"
    severity: critical | warning | info
    file: "{파일 경로}"
    line: {라인 번호} (가능하면)
    issue: "{문제}"
    suggestion: "{수정 제안}"

summary:
  files_checked: {N}
  total_findings: {N}
  critical: {N}
  warning: {N}
  pass: {true | false}
```
