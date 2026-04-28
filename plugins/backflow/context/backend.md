# 백엔드 프로젝트 컨텍스트

모든 backflow 스킬이 참조하는 프로젝트 설정입니다.
프로젝트 초기화 시 1회 작성하고, 기술 스택 변경 시 갱신하세요.

## 프레임워크

```yaml
framework:
  name: ""               # NestJS | Express | Fastify | Spring Boot | Django | FastAPI
  version: ""            # 예: 10.x
  language: ""           # TypeScript | Java | Python | Go | Kotlin
  language_version: ""   # 예: 5.x
```

## 데이터베이스

```yaml
database:
  primary: ""            # PostgreSQL | MySQL | MongoDB | SQLite
  orm: ""                # Prisma | TypeORM | Drizzle | Sequelize | SQLAlchemy | GORM
  migration_tool: ""     # orm 내장 | knex | flyway | alembic
  naming_convention: ""  # snake_case | camelCase
  schema_path: ""        # 예: prisma/schema.prisma, src/entities/
```

## 디렉토리 구조

```yaml
structure:
  src_root: ""           # 예: src/
  controller_dir: ""     # 예: src/controllers 또는 src/modules/*/controllers
  service_dir: ""        # 예: src/services 또는 src/modules/*/services
  repository_dir: ""     # 예: src/repositories 또는 src/modules/*/repositories
  entity_dir: ""         # 예: src/entities 또는 src/modules/*/entities
  middleware_dir: ""     # 예: src/middleware
  dto_dir: ""            # 예: src/dto 또는 src/modules/*/dto
  util_dir: ""           # 예: src/common 또는 src/lib
  test_dir: ""           # 예: src/**/*.spec.ts 또는 tests/
  module_pattern: ""     # flat | feature-module | domain-driven
  naming: "kebab-case"   # 파일명 컨벤션
```

## 인증 / 인가

```yaml
auth:
  strategy: ""           # jwt | session | oauth2 | api-key
  guard_pattern: ""      # decorator | middleware | interceptor
  role_model: ""         # RBAC | ABAC | none
  token_location: ""     # Authorization header | cookie
```

## 보안 검증 (Phase 2)

`validate-security` 가 사용하는 scan scope 와 policy default 입니다.
secret value, token, credential 은 절대 저장하지 마세요.

```yaml
security_validation:
  exposure: "public"     # public | internal | mixed
  public_route_allowlist:
    - "/health"
    - "/metrics"
  auth_bypass_allowlist:
    - "/health"
    - "/docs"
    - "/webhooks/**"
  privileged_role_names: ["admin", "owner"]
  tenant_context_keys: ["tenant_id", "workspace_id", "organization_id"]
  sensitive_fields:
    - "password"
    - "password_hash"
    - "token"
    - "refresh_token"
    - "secret"
    - "api_key"
    - "authorization"
    - "ssn"
    - "card_number"
  session_auth_requires_csrf: true
  ssrf_allowed_hosts_env: "SSRF_ALLOWED_HOSTS"
  upload_routes: ["/uploads/**"]
  webhook_routes: ["/webhooks/**"]
  report_min_severity: "info"  # info | warning | critical
  exclude_globs:
    - "node_modules/**"
    - "dist/**"
    - "build/**"
    - "coverage/**"
    - ".git/**"
```

## API 스타일

```yaml
api:
  style: ""              # REST | GraphQL | gRPC
  versioning: ""         # url-prefix(/api/v1) | header | none
  base_path: ""          # 예: /api/v1
  doc_tool: ""           # Swagger/OpenAPI | none
  request_validation: "" # class-validator | zod | joi | pydantic
  response_format: |
    // 프로젝트의 응답 래핑 패턴
    // 예:
    // { success: true, data: T }
    // { success: false, error: { code: string, message: string } }
```

## API 계약

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

## 에러 핸들링

```yaml
error_handling:
  strategy: ""           # exception-filter | error-middleware | global-handler
  error_class: ""        # 예: HttpException, AppError
  error_code_enum: ""    # 예: src/errors/codes.ts — 에러 코드 enum 파일 (impl-error-codes 출력)
  http_mapping_file: ""  # 예: src/errors/http-mapping.ts — code → HTTP status 매핑 파일
  i18n_enabled: true     # true: i18n JSON 생성 | false: 메시지 코드에 inline
  i18n_output_dir: ""    # 예: src/locales — errors.{lang}.json 출력 디렉토리 (i18n_enabled=true 시)
  languages: ["ko", "en"] # 생성할 i18n 언어 목록 (TS §에러 코드 맵 컬럼과 1:1)
  logging: ""            # winston | pino | bunyan | built-in (deprecated — observability.logger 로 이전)
  pattern: |
    // 프로젝트의 에러 핸들링 패턴
```

## 관측성 (Observability)

```yaml
observability:
  # 라이브러리 선택 (canonical 값. 실제 import 는 skill 이 매핑)
  logger: ""                          # pino | winston | bunyan | structlog | logging | slog | zerolog | slf4j-logback | tracing
  tracing_lib: ""                     # otel-sdk-node | opentelemetry-distro | otel-go | otel-java-agent | otel-rust

  # 로깅 동작
  log_format: "json"                  # json | text(dev only)
  log_level_default: "info"           # debug | info | warn | error
  log_level_env: "LOG_LEVEL"          # 런타임 override env 변수 이름

  # 트레이싱
  sampling_rate_dev: 1.0              # 0.0 ~ 1.0
  sampling_rate_prod: 0.1             # 0.0 ~ 1.0 (override: OTEL_SAMPLING_RATE_PROD env)
  trace_propagation: "W3C"            # W3C (default) | b3 (legacy)

  # 태그·마스킹
  required_tags: ["service", "environment", "request_id", "trace_id"]
  optional_tags: []                   # 예: ["user_id", "tenant_id"]
  sensitive_field_masking: ["password", "token", "ssn", "card_number"]

  # 상관 관계
  correlation_header: "X-Request-Id"  # X-Request-Id | X-Correlation-Id (Traceparent 는 사용 금지 — trace_propagation 전용)
  error_code_tag: true                # ErrorCode 자동 log tag 주입 (TS §4 에러 코드 맵 존재 전제)

  # 리소스 식별
  service_name: ""                    # OTel resource attribute (없으면 framework.name 사용)
  otel_endpoint_env: "OTEL_EXPORTER_OTLP_ENDPOINT"  # OTel Collector 위치 env (벤더는 Collector 설정)

  # 출력 파일 경로 (impl-observability 가 작성)
  context_file: ""                    # 예: src/observability/context.ts (AsyncLocalStorage / contextvars / MDC 추상)
  logger_file: ""                     # 예: src/observability/logger.ts
  request_id_middleware_file: ""      # 예: src/middleware/request-id.ts
  tracing_file: ""                    # 예: src/observability/tracing.ts
  error_tag_file: ""                  # 예: src/observability/error-tag.ts (error_code_tag=true 시)

  # App entrypoint — skill 이 tracing import + middleware 등록을 추가
  bootstrap_file: ""                  # 예: src/main.ts | src/server.ts | src/app.module.ts (framework convention)

  # Phase 2 예정: metrics_file / metrics 계측 — 이 phase 에서는 다루지 않음
```

## 테스트

```yaml
testing:
  runner: ""             # jest | vitest | pytest | JUnit
  unit_pattern: ""       # *.spec.ts | *.test.ts | test_*.py
  integration_pattern: ""# *.e2e-spec.ts | *.int.test.ts
  mock_strategy: ""      # jest.mock | sinon | testcontainers
  db_strategy: ""        # in-memory | testcontainers | sqlite | truncate
  coverage_target: ""    # 예: 80%
```

## 외부 서비스

```yaml
external_services:
  message_queue: ""      # none | Redis/BullMQ | RabbitMQ | SQS | Kafka
  cache: ""              # none | Redis | Memcached
  storage: ""            # none | S3 | GCS | local
  email: ""              # none | SendGrid | SES | Resend
  realtime: ""           # none | SSE | WebSocket | Socket.IO
```

## 파일 업로드 (Phase 1 (5))

```yaml
file_upload:
  storage_vendor: ""              # "" (local only) | s3 | gcs | r2 | minio
  storage_bucket_env: "STORAGE_BUCKET"
  storage_endpoint_env: "STORAGE_ENDPOINT"
  storage_region_env: "STORAGE_REGION"
  storage_local_root_env: "STORAGE_LOCAL_ROOT"
  presigned_ttl_sec: 900
  meta_table: "upload_meta"
  uploads_module_dir: "src/uploads"
  storage_subdir: "storage"
  resize_subdir: "resize"
  selected_storage_filename: "selected-storage.ts"
  resize_worker_pattern: "central"   # central | per-variant
  resize_presets:
    thumb_64: { width: 64, height: 64, fit: "cover", format: "webp", quality: 80 }
    thumb_256: { width: 256, height: 256, fit: "cover", format: "webp", quality: 85 }
    card_512: { width: 512, height: 512, fit: "contain", format: "webp", quality: 85 }
  file_id_strategy: "uuid_v7"
  callback_required: true         # Phase 1 항상 true 강제 (false 는 Phase 2)
  scan_on_complete: false         # Phase 2
  metadata_schema_version: 1
```

## Webhook (Phase 1 (6))

```yaml
webhook:
  webhook_module_dir: "src/webhooks"
  signatures_subdir: "signatures"
  selected_signature_filename: "selected-signature.ts"
  dispatch_file: "dispatch.ts"
  idempotency_table: "webhook_idempotency"
  idempotency_entity_path: "src/webhooks/idempotency.entity.ts"
  idempotency_ttl_days: 30
  default_timeout_sec: 30
  bypass_auth_routes: ["/webhooks/**"]
  signature_clock_skew_sec: 300
  always_200_default: true
  retry_status_code: 503
  enqueue_only: true
  duplicate_delivery_logging: true
```
